# CloudSale → Warehouse Architecture Patterns

A reference for porting the CloudSale (PHP) backend architecture into Warehouse
(Python 3.12+ / FastAPI / SQLAlchemy async). For each pattern it documents the
CloudSale PHP implementation, the Warehouse Python equivalent, and the current
build status in Warehouse.

> Source projects:
> - CloudSale (PHP): `D:\Projects\CloudSale`
> - Warehouse (Python): `D:\Projects\Warehouse`

## How to read this document

Every section follows the same shape:

1. **Pattern** — what the abstraction is and why it exists.
2. **CloudSale (PHP)** — the original implementation.
3. **Warehouse (Python/FastAPI)** — the mapped equivalent to use.
4. **Status** — one of:
   - **Built** — already implemented in Warehouse, matches the pattern.
   - **Partial** — exists but incomplete or simplified versus CloudSale.
   - **To build** — not yet present; this doc is the spec.

## Status summary

| # | Pattern | CloudSale source | Warehouse target | Status |
|---|---|---|---|---|
| 1 | IoC container (suffix auto-resolution) | `infrastructure/Ioc.php` | `app/infrastructure/ioc.py` | Built |
| 2 | GenericFactory / DataFactory / ErrorFactory | `infrastructure/*Factory.php` | `app/infrastructure/ioc.py` | Partial |
| 3 | AbstractController | `controllers/AbstractController.php` | `app/controllers/base_controller.py` | Built |
| 4 | AbstractService | `services/AbstractService.php` | `app/services/abstract_service.py` | Built |
| 4a | AbstractMapper / ActiveUserMapper (context holder) | `mappers/AbstractMapper.php`, `mappers/ActiveUserMapper.php` | `app/mappers/abstract_mapper.py`, `app/mappers/current_user_mapper.py` | Built |
| 5 | AbstractStorage | `storages/AbstractStorage.php` | `app/storages/abstract_storage.py` | Partial |
| 6 | AbstractData (value object) | `data/AbstractData.php` | `app/data/abstract_data.py` | Built |
| 7 | AbstractDataCollection | `data/AbstractDataCollection.php` | `app/data/data_collection.py` | Built |
| 8 | AbstractRequest + validation engine | `requests/AbstractRequest.php`, `infrastructure/RequestValidator.php` | Pydantic + `app/helpers/expand_validator.py` | Partial |
| 9 | AbstractError + ErrorDefinitions | `errors/AbstractError.php`, `definitions/ErrorDefinitions.php` | `app/errors/abstract_error.py` | To build |
| 10 | TransactionHelper (deadlock retry) | `helpers/TransactionHelper.php` | `app/infrastructure/transaction.py` | Partial |
| 11 | RequestHelper | `helpers/RequestHelper.php` | FastAPI request objects | Built (by framework) |
| 12 | ResponseHelper | `helpers/ResponseHelper.php` | FastAPI responses + exception handlers | Partial |
| 13 | Storage query / filter / lock / pagination | `storages/ProductStorage.php`, `AbstractStorage.php` | SQLAlchemy Core/ORM | To build |
| 14 | Service orchestration (no DB access) | `services/Product/*.php` | `app/services/<domain>/*.py` | Built (auth only) |

---

## 1. IoC container — suffix-based auto-resolution

### Pattern

A per-request container resolves collaborators by **class name**. The class-name
suffix selects the layer; the class is loaded from a conventional file path. No
explicit registration. In CloudSale the magic method `__get` triggers resolution
on any property read; in Python the equivalent is `__getattr__`.

### CloudSale (PHP)

`infrastructure/Ioc.php` dispatches on the class-name suffix and constructs the
target with `$this` (the container) as the first argument:

```php
public function __get($name) {
    return $this->getDependency($name);
}

public function getDependency($name, $for = null) {
    if (substr($name, -7) == 'Request')      { $this->load($name, 'requests', true, 'GenericFactory'); }
    elseif (substr($name, -7) == 'Service')  { $this->load($name, 'services', true); }
    elseif (substr($name, -4) == 'Data')     { $this->load($name, 'data', false, 'DataFactory'); }
    elseif (substr($name, -5) == 'Error')    { $this->load($name, 'errors', true, 'ErrorFactory'); }
    elseif (substr($name, -7) == 'Storage')  { $this->load($name, 'storages'); }
    elseif (substr($name, -6) == 'Helper')   { $this->load($name, 'helpers'); }
    elseif (substr($name, -11) == 'Definitions') { $this->loadDefinitions($name); }
    elseif ($name == 'db') { /* only storages */ $this->loadDb(); }
    else { throw new \InvalidArgumentException('Dont know how to load: '. $name); }
    return $this->$name;
}
```

Nested layers (`services`, `requests`, `errors`) encode the domain folder in the
class name by reading the **second uppercase run** (`strcspn(... 'A-Z' ...)`), so
`ProductCreateService` → `services\Product\ProductCreateService`. Flat layers
(`storages`, `helpers`, `mappers`) map directly. A `classMap` allows overrides
(`override()` / `useDefault()`) for test doubles.

### Warehouse (Python/FastAPI)

`app/infrastructure/ioc.py` — `Ioc.__getattr__` dispatches on the same suffix
table. Two refinements over CloudSale:

- **Strategy B path derivation**: the module file name is the snake_case of the
  class name, and the resolver *scans the layer package recursively*
  (`pkgutil.walk_packages`) instead of encoding the domain in the class name. So
  domain nesting (`services/auth/auth_service.py`) is discovered, not parsed out
  of the class name.
- **Lifetime is request-scoped**: a fresh `Ioc` per HTTP request via the
  `get_ioc` FastAPI dependency. CloudSale's container was effectively
  per-request too, but Warehouse makes it explicit and forbids module-level
  caching.

```python
_SUFFIX_TO_PACKAGE = {
    "Service": "app.services",
    "Storage": "app.storages",
    "Mapper":  "app.mappers",
    "Request": "app.requests",
    "Error":   "app.errors",
}
_INSTANTIATED_SUFFIXES = frozenset({"Service", "Storage", "Mapper"})  # rest are factories

def __getattr__(self, name: str) -> Any:
    if name.startswith("_"):
        raise AttributeError(name)
    suffix = self._match_suffix(name)
    if suffix is None:
        raise IocResolutionError(...)
    if suffix in _INSTANTIATED_SUFFIXES:
        return self._resolve_instance(name)   # memoized per request
    target = self._load_class(name, suffix)
    return ErrorFactory(target) if suffix == "Error" else GenericFactory(target)
```

Resolution mapping (matches `docs/architecture/IOC.md`):

| Suffix | Package root | Returns |
|---|---|---|
| `*Service` | `app.services` (nested by domain) | instance (memoized) |
| `*Storage` | `app.storages` (flat) | instance (memoized) |
| `*Mapper` | `app.mappers` (flat) | instance (memoized) |
| `*Request` | `app.requests` (nested by domain) | `GenericFactory` |
| `*Error` | `app.errors` (nested by domain) | `ErrorFactory` |

`_CLASS_CACHE` caches resolved **types** at process level (immutable, safe);
`_instances` holds live instances per request and is GC'd with the container.

### Status: **Built**

Differences from CloudSale to be aware of when porting:

- `*Mapper` is now wired into the Warehouse container (see section 4a below).
  Helpers remain plain importable modules (`app/helpers/jwt.py`, `password.py`,
  `security.py`, `expand_validator.py`), not container-resolved. No `*Helper`
  suffix.
- No `*Data` or `*Definitions` suffix is wired. Decide per pattern below whether
  to add to `_SUFFIX_TO_PACKAGE`.
- No `classMap` override mechanism. In Python, tests substitute collaborators by
  monkeypatching the module or assigning into `ioc._instances[name]` before use.
  Add an `override(name, instance)` method if test ergonomics demand it.
- `db` access guard ("only storages can access the database") is not enforced by
  type in Warehouse — `ioc.session` is reachable from any layer. The
  architecture rule (DB access only in storages) is enforced by convention and
  review, not by the container.

---

## 2. Factories — GenericFactory / DataFactory / ErrorFactory

### Pattern

For classes that are *constructed on demand with arguments* (requests, data,
errors) the container returns a thin factory rather than a singleton. The
factory closes over the container and the target class, exposing `.get(...)`
(and for data, `.make(...)` / `.makeCollection(...)`).

### CloudSale (PHP)

```php
// GenericFactory — requests
class GenericFactory {
    public function get(...$params) { return new $this->className($this->Ioc, ...$params); }
}

// DataFactory — data value objects + collections
class DataFactory {
    public function make($data, $defaults = null) { return new $this->className($this->Ioc, $data, $defaults); }
    public function makeCollection(array $items = array()) {
        $collection = new ($this->className.'Collection')();
        foreach ($items as $item) { $collection->add(new $this->className($this->Ioc, $item)); }
        return $collection;
    }
    public function getFields() { return $this->className::FIELDS; }
}

// ErrorFactory — errors, with the throw helper
class ErrorFactory {
    public function get(...$params) { return new $this->className($this->Ioc, ...$params); }
    public function throwException(...$params) {
        (new $this->className($this->Ioc, ...$params))->throwException();
    }
}
```

Usage in CloudSale services/storages:

```php
$this->ProductData->make([...]);                    // DataFactory.make
$this->ProductData->makeCollection($rows);          // DataFactory.makeCollection
$this->ProductNameAlreadyExistsError->throwException($name);  // ErrorFactory.throwException
$this->ProductCreateRequest->get($body);            // GenericFactory.get
```

### Warehouse (Python/FastAPI)

`app/infrastructure/ioc.py` already defines `GenericFactory` and `ErrorFactory`:

```python
class GenericFactory:
    def __init__(self, target: type) -> None: self._target = target
    @property
    def target(self) -> type: return self._target
    def get(self, *args, **kwargs): return self._target(*args, **kwargs)

class ErrorFactory(GenericFactory):
    pass
```

Differences and what to build:

- **`.target` property** is the Python idiom CloudSale lacks. Controllers use it
  for `except` clauses: `except self.InvalidCredentialsError.target:`. Keep it.
- **`ErrorFactory.throwException`** is *not* implemented in Warehouse. CloudSale's
  `throwException()` wraps the error in an HTTP exception and raises in one call.
  In Warehouse the current style is `raise self.SomeError.get("msg")`. When the
  full error model (section 9) lands, add a `throw(*args)` /
  `throw_exception(*args)` method to `ErrorFactory` so call sites read
  `self.ProductNameAlreadyExistsError.throw(name)`.
- **`DataFactory`** does **not** exist in Warehouse, and `*Data` is **not** wired
  into the container. Warehouse data classes are constructed directly
  (`AuthUser.from_row(row)`) rather than via `ioc.AuthUser.make(...)`. See
  section 6 for the recommendation (likely keep `from_row` and skip the
  container-resolved DataFactory unless the `make/makeCollection` ergonomics are
  wanted).

### Status: **Partial**

`GenericFactory`/`ErrorFactory` built; `DataFactory` and `throwException`/`throw`
to build.

---

## 3. AbstractController

### Pattern

Base controller owns the single container injection point and proxies attribute
access to the container, so route methods read `self.SomeService` /
`self.SomeError` without ever naming the container.

### CloudSale (PHP)

```php
abstract class AbstractController {
    private $Ioc;
    public function __construct($Ioc) { $this->Ioc = $Ioc; }
    public function __get($name) {
        $this->$name = $this->Ioc->getDependency($name, 'Controller');
        return $this->$name;
    }
    public function options() { /* builds Allow header from defined http verbs */ }
}
```

CloudSale routes one PHP file per resource (`Products::get()`, `Products::post()`).

### Warehouse (Python/FastAPI)

`app/controllers/base_controller.py`:

```python
class BaseController:
    def __init__(self, ioc: Ioc = Depends(get_ioc)) -> None:
        self._ioc = ioc
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

The injection point is `Depends(get_ioc)` resolved through FastAPI's DI on the
controller's `__init__`. Concrete controllers subclass `BaseController` and
become FastAPI dependencies themselves. See `app/controllers/auth/router.py`:

```python
class AuthController(BaseController):
    async def login(self, body: LoginRequest) -> dict:
        try:
            return await self.AuthService.login(email=body.email, password=body.password)
        except self.InvalidCredentialsError.target:
            raise HTTPException(status_code=401, detail="Invalid credentials", ...)

@router.post("/login")
async def login(body: LoginRequest, ctrl: AuthController = Depends(AuthController)) -> dict:
    return await ctrl.login(body)
```

Key mapping notes:

- CloudSale's `__get` *caches the resolved dependency onto the instance*
  (`$this->$name = ...`). Python's `__getattr__` does not cache on the instance,
  but the `Ioc` memoizes services/storages, so repeated `self.AuthService`
  returns the same instance — equivalent behaviour.
- CloudSale's HTTP `OPTIONS`/`Allow` handling is provided by FastAPI/Starlette
  automatically; no port needed.
- The thin module-level `@router.post` wrapper exists because FastAPI binds
  routes to functions, not to methods. Keep the wrapper minimal — it only
  delegates to the controller method.

### Status: **Built**

---

## 4. AbstractService

### Pattern

Base service holds the container and proxies attribute access so business logic
reads `self.SomeStorage` / `self.SomeError` / `self.settings`. Services contain
**all** business logic, coordinate storages, never touch the DB directly, and
never open transactions.

### CloudSale (PHP)

```php
abstract class AbstractService {
    protected $Ioc;
    public function __construct($Ioc) { $this->Ioc = $Ioc; }
    public function __get($name) {
        $this->$name = $this->Ioc->getDependency($name, 'Service');
        return $this->$name;
    }
    protected function throwError($errorCode, $error, $errorParams = [], $details = false) {
        $ex = new \exceptions\ClientErrors\BadRequest();
        $ex->setError($errorCode, $error, $errorParams, $details);
        throw $ex;
    }
}
```

Concrete service (`services/Product/ProductCreateService.php`):

```php
class ProductCreateService extends \services\AbstractService {
    public function create(\requests\Product\ProductCreateRequest $requestData) {
        $existing = $this->ProductStorage->getByName($requestData->name, DB_WRITE_LOCK);
        if ($existing) { $this->ProductNameAlreadyExistsError->throwException($requestData->name); }
        $productData = $this->ProductData->make([...]);
        $this->ProductStorage->create($productData);
        return $productData;
    }
}
```

Note CloudSale's granularity: **one service class per operation**
(`ProductCreateService`, `ProductUpdateService`, `ProductDeleteService`,
`ProductCollectionFilterService`).

### Warehouse (Python/FastAPI)

`app/services/abstract_service.py`:

```python
class AbstractService:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

Concrete service (`app/services/auth/auth_service.py`) coordinates a storage and
raises container errors, with no DB access of its own:

```python
class AuthService(AbstractService):
    async def login(self, email: str, password: str) -> dict:
        user = await self.NotImplementedUserLookupService.get_by_email(email, db_name)
        if user is None:
            verify_password(password, _DUMMY_HASH)  # timing-safe
            raise self.InvalidCredentialsError.get("Invalid credentials")
        ...
        await self.RefreshTokenStorage.save(...)
        return {"access_token": ..., "token_type": "bearer", "refresh_token": ...}
```

Mapping notes:

- CloudSale's `throwError(...)` convenience is replaced by the container error
  factories (`raise self.SomeError.get(...)`), which is closer to Python idiom.
  When section 9's error model lands, prefer `self.SomeError.throw(...)`.
- **Service granularity is a choice.** CloudSale uses one-service-per-operation.
  Warehouse `AuthService` groups `login`/`refresh`/`logout` on one class.
  Warehouse's RULES treat the service as "all business logic" without mandating
  one-op-per-class. Recommendation: group cohesive operations per aggregate
  (`ProductService.create/update/delete/list`) unless an operation grows large
  enough to warrant its own class. Either way the IoC resolves both styles.

### Status: **Built** (auth domain only; other domains to follow this template)

---

## 4a. AbstractMapper / ActiveUserMapper — per-request context holder

### Pattern

A Mapper is a per-request context holder, not a DTO and not a service. It holds
mutable state set once per request (e.g. verified JWT identity), provides
computed properties and role-check methods, and may lazy-load related data from
Storage cached on the instance. The IoC container resolves `*Mapper` classes from
a flat `mappers/` namespace, instantiates them, and memoizes them for the
lifetime of the request.

### CloudSale (PHP)

`mappers/AbstractMapper.php` — container-proxying base identical to
`AbstractService`. Concrete `ActiveUserMapper` holds the verified user row after
an explicit `init($userData)` call, exposes `getId()`, `getUsername()`,
`isEnabled()`, role-check methods (`isWaiter()`/`isManager()`), and lazy-loads
`getApiKey()` from `ApiKeyStorage` cached on the instance.

CloudSale's IoC resolves `*Mapper` from a flat `mappers/` namespace (same
nesting rule as `storages/`).

### Warehouse (Python/FastAPI)

`app/mappers/abstract_mapper.py` — `AbstractMapper`:

```python
class AbstractMapper:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

`app/mappers/current_user_mapper.py` — `CurrentUserMapper` (Warehouse equivalent
of `ActiveUserMapper`). Reads verified JWT claims from `ioc.claims` (`TokenData |
None`) — no explicit `init()` step required:

```python
class CurrentUserMapper(AbstractMapper):
    def is_initialized(self) -> bool: ...     # True when ioc.claims is not None
    @property
    def user_id(self) -> str: ...             # claims.sub; raises UnauthenticatedError if no claims
    @property
    def tenant_id(self) -> str: ...           # claims.tenant_id; raises UnauthenticatedError if no claims
    @property
    def role(self) -> str: ...                # claims.role; raises UnauthenticatedError if no claims
    def is_admin(self) -> bool: ...           # role == "admin"
    def is_manager(self) -> bool: ...         # role == "manager"
```

`app/errors/auth/unauthenticated_error.py` — `UnauthenticatedError(Exception)`:
raised by identity properties when no verified claims are present. Caught via
`ioc.UnauthenticatedError.target` (same `ErrorFactory` pattern).

Key design differences from CloudSale:

- Warehouse reads claims from the container (`ioc.claims`) rather than requiring
  an explicit `init()` call. The container is the single source of truth.
- `UnauthenticatedError` is raised on unauthenticated access (CloudSale throws
  when uninitialized — same semantics, different trigger).
- Lazy full-profile load (`get_profile()`) is out of scope until a SQL
  `UserStorage` exists. The extension point is documented in the class; currently
  identity claims only.
- Role literals (`"admin"`, `"manager"`) match the JWT `role` claim issued by
  `create_access_token`. A `Role` enum is a follow-up (not yet built).

### Status: **Built**

---

## 5. AbstractStorage

### Pattern

The only layer that touches the database. Proxies the container, exposes shared
helpers for lock handling, field selection, filter processing and pagination.
Never opens transactions; operates inside the controller-started transaction.
Assigns generated primary keys back onto the passed-in Data object.

### CloudSale (PHP)

```php
abstract class AbstractStorage {
    private $Ioc;
    public function __construct($Ioc) { $this->Ioc = $Ioc; }
    public function __get($name) {
        $this->$name = $this->Ioc->getDependency($name, 'Storage');  // 'Storage' permits ->db
        return $this->$name;
    }
    protected function processLock($lockType) {
        if ($lockType === DB_WRITE_LOCK)      { $this->db->for_update(); }
        elseif ($lockType === DB_READ_LOCK)   { $this->db->for_read(); }
    }
    protected function sqlLock($lockType) {
        if ($lockType === DB_WRITE_LOCK)      { return 'FOR UPDATE'; }
        elseif ($lockType === DB_READ_LOCK)   { return 'LOCK IN SHARE MODE'; }
        return '';
    }
    protected function selectFields($fields, $allowedFields) {
        // splits CSV, validates each field against the Data FIELDS map, then db->select()
    }
    protected function processPageFilters($filters) {
        $pagination = $this->PaginationData->make(['all_pages' => 0]);
        $pagination->current_page    = empty($filters['page'])     ? 1   : $filters['page'];
        $pagination->results_per_page = empty($filters['per_page']) ? 100 : $filters['per_page'];
        $this->db->limit($pagination->results_per_page, ($pagination->current_page - 1) * $pagination->results_per_page);
        return $pagination;
    }
}
```

### Warehouse (Python/FastAPI)

`app/storages/abstract_storage.py` currently provides only the container proxy:

```python
class AbstractStorage:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

Storages reach the DB via `self.session` (an `AsyncSession`) or `self.redis`.
The existing `RefreshTokenStorage` is a Redis-only storage and does not exercise
the SQL helpers.

To reach parity with CloudSale's SQL helpers, add to `AbstractStorage`:

- **Lock handling** — translate `lock_type` into SQLAlchemy
  `.with_for_update()` (write) / `.with_for_update(read=True)` (shared). Define a
  small enum `DbLock.WRITE / DbLock.READ` instead of MySQL `LOCK IN SHARE MODE`
  string literals (Postgres uses `FOR UPDATE` / `FOR SHARE`).
- **Field selection** — validate requested column names against the Data
  field set (section 6) before building a partial `select()`.
- **Pagination** — a `process_page_filters(filters) -> Pagination` helper that
  computes `limit`/`offset` from `page`/`per_page` (default 100) and a total
  count. CloudSale uses MySQL `SELECT FOUND_ROWS()`; Postgres has no equivalent,
  so use a separate `COUNT(*)` query or a window function
  `count(*) OVER ()` on the page query.

Mapping notes:

- **Storage assigns the PK back to the Data object** (CloudSale:
  `$productData->product_id = $this->db->insert_id();`). In SQLAlchemy use
  `RETURNING` (Core) or flush + read `obj.id`, then set it on the returned Data.
  This is an explicit architecture rule in `RULES.md`.
- **Tenant scoping**: every Warehouse storage query MUST filter by
  `self.tenant_id` (sourced from JWT). CloudSale had no multi-tenancy. This is a
  Warehouse-specific addition with no CloudSale counterpart — do not copy
  CloudSale queries verbatim; add the tenant predicate.
- **No transaction control in storage** (same rule in both projects).

### Status: **Partial** (container proxy built; SQL lock/field/pagination helpers and the SQLAlchemy query patterns to build)

---

## 6. AbstractData — typed value object

### Pattern

A value object with a fixed field set and per-field type coercion. Reads/writes
go through whitelisted fields only; unknown fields raise. Supports
`from_row`/`make`, `toArray`, JSON serialization, diffing
(`extractDifferences`), and merge (`injectInto`).

### CloudSale (PHP)

```php
abstract class AbstractData implements \JsonSerializable {
    const FIELDS = array();           // field => type ('int','float','boolean','string','datetime')
    public function __construct($Ioc, $data, $defaults = null) {
        // copy whitelisted fields, applying fixType() per FIELDS
    }
    public function __get($name)  { /* only FIELDS allowed, else DomainException */ }
    public function __set($name, $value) { $this->_->$name = $this->fixType(static::FIELDS[$name], $value); }
    public function getFields() { return static::FIELDS; }
    public function extractDifferences($data) { /* returns a new Data with only changed fields */ }
    public function injectInto($another) { /* copies own fields onto another Data */ }
    public function notEmpty() { return !empty((array)$this->_); }
    public function toArray() { return (array)$this->_; }
    public function jsonSerialize() { return $this->_; }
    public function fixType($type, $value) {
        switch ($type) { case 'int': return (int)$value; case 'float': return (float)$value; ... }
    }
}

class ProductData extends AbstractData {
    const FIELDS = array('product_id'=>'int','name'=>'string','price'=>'float','measure_unit'=>'string');
}
```

The diff/merge pair powers PATCH updates (`ProductUpdateService`):
`extractDifferences(request.toArray())` → if `notEmpty()`, persist only changes,
then `injectInto` the canonical object.

### Warehouse (Python/FastAPI)

`app/data/abstract_data.py` — `AbstractData` is the built base mixin for
`@dataclass` Data classes. It carries the CloudSale `FIELDS` map and per-field
type coercion, adapted to Python dataclasses (field STORAGE stays the dataclass
mechanism — no PHP `$this->_` shadow object).

```python
@dataclass
class RecipeData(AbstractData):
    FIELDS = {"id": "int", "name": "string", "products": "expanded"}
    id: int
    name: str
    products: list[Any] = field(default_factory=list)
```

As-built members:

- **`FIELDS: ClassVar[dict[str, str]]`** — subclass declares `{field: type_token}`.
  Authoritative field whitelist and the source for type coercion. Type tokens:
  module-level constants `INT="int"`, `FLOAT="float"`, `STRING="string"`,
  `BOOL="bool"`, `DATETIME="datetime"`, `EXPANDED="expanded"`.
- **`EXPANDED` token** + `ExpandedField = list[Any]` alias — marks list-valued
  nested child fields. `expanded` fields are NOT read from the DB row by the
  default `from_row`; they default to `[]` and are populated later by
  `DataCollection.expand_property`.
- **`from_row(cls, row) -> AbstractData`** (`@classmethod`) — maps `FIELDS` keys
  from the row (mapping or attribute object), applies `fix_type` per field,
  defaults `expanded` fields to `[]`. Subclasses may override (the existing
  `AuthUser.from_row` style stays valid).
- **`fix_type(type_token, value) -> Any`** (`@staticmethod`) — `None` passes
  through; `int`/`float`/`str`/`bool` cast; `datetime` parsed to tz-aware UTC;
  `expanded` and unknown tokens return the value unchanged (list passthrough).
- **field guard** — `__setattr__` rejects writes to names not in `FIELDS`
  (leading-underscore/dunder names allowed). Dataclass `__init__` only sets
  declared fields, so construction is unaffected; the guard covers
  post-construction dynamic sets (e.g. `DataCollection.expand_property`).
- **`to_dict() -> dict[str, Any]`** — returns the field map in `FIELDS` order;
  includes `expanded` fields as their list value. For response shaping and
  storage `insert(...).values(...)`.

`AuthUser` deliberately stays a plain `@dataclass` (NOT `AbstractData`): it has no
expanded fields, its `from_row` already casts, and it carries `password_hash`
which must never be serialized via `to_dict()`. A code comment documents this.

Still NOT built (deferred until a PATCH endpoint needs it):

- `extract_differences(other_fields) -> Data` — compute changed fields for PATCH,
  paired with Pydantic `model_fields_set` (CloudSale `hasKey` analogue).
- `inject_into(other)` / merge.

### Status: **Built** (`AbstractData` base with `FIELDS`/`expanded` token, `from_row`, `fix_type`, field guard, `to_dict`; diff/merge `extract_differences`/`inject_into` deferred until the PATCH-diff workflow is adopted)

---

## 7. AbstractDataCollection

### Pattern

A typed, iterable, countable, JSON-serializable wrapper around a list of Data
objects with collection utilities: pluck a property across items
(`extractPropertyValues`), index by a property
(`extractPropertyValuesAsKeys`), group by a property, expand a child collection
onto each item (`expandProperty`), and sorters.

### CloudSale (PHP)

```php
abstract class AbstractDataCollection implements \Iterator, \Countable, \JsonSerializable {
    public function jsonSerialize() { return array_values($this->collection); }
    // Iterator: rewind/current/key/next/valid ; Countable: count
    public function extractPropertyValues($property) { /* [$item->$property, ...] */ }
    public function extractPropertyValuesAsKeys($property) { /* [$item->$property => $item] */ }
    public function toArrayGroupedByPropertyValuesAsKeys($property, $unset=false) { /* group */ }
    public function expandProperty($expanded, $groupKey, $groupedValues) {
        foreach ($this->collection as $item) { $item->$expanded = $groupedValues[$item->$groupKey] ?? []; }
    }
    public function sortByIntegerPropertyValueAscending($property) { /* usort */ }
    // ...string sorters
}

class ProductDataCollection extends AbstractDataCollection {
    public function add(ProductData $item) { $this->collection[] = $item; }
}
```

`expandProperty` is the join-in-memory pattern: load recipes, load their products
grouped by `recipe_id`, then `expandProperty('products','recipe_id',$grouped)` to
nest children without N+1 queries.

### Warehouse (Python/FastAPI)

`app/data/data_collection.py` — `DataCollection[T]` is the built generic typed
wrapper around `list[T]` (`T = TypeVar("T", bound=AbstractData)`). It is a thin
wrapper (comprehension-based methods), not a framework.

```python
T = TypeVar("T", bound=AbstractData)

class DataCollection(Generic[T]):
    def __init__(self, items: list[T] | None = None) -> None: ...
```

As-built members:

- **construction / mutation** — `DataCollection(items=None)` (no mutable default;
  defaults to `[]` internally), `add(item)`.
- **sequence protocol** — `__iter__`, `__len__`, `__getitem__`, `__bool__`.
- **`expand_property(expanded_property, group_key_property, grouped_values)`** —
  for each item, sets `item.<expanded_property> =
  grouped_values.get(item.<group_key_property>, [])` (missing key -> `[]`). Direct
  port of CloudSale `expandProperty`. Relies on `AbstractData`'s field guard to
  reject a misnamed `expanded_property`.
- **`extract_property_values(property_name) -> list`** —
  `[getattr(i, property_name) for i in items]`.
- **`extract_property_values_as_keys(property_name) -> dict`** —
  `{getattr(i, property_name): i for i in items}` (last item wins on collision).
- **`group_by_property(property_name) -> dict[key, list]`** — groups items into
  lists keyed by the property. Used to build the `grouped_values` argument for
  `expand_property` on a CHILD collection before attaching to a PARENT collection.
- **`to_list() -> list[T]`** / **`to_dicts() -> list[dict]`** — plain list and
  serialized list (`item.to_dict()`), for response shaping.

Single-level parent->children expand only (matches CloudSale `expandProperty`
semantics). Recursive expand-within-expand is not supported.

CloudSale sorters (`sortByIntegerPropertyValueAscending`, string sorters) are NOT
ported — Python `sorted(collection, key=...)` covers them.

### Status: **Built** (`DataCollection[T]` with sequence protocol, `add`, `expand_property`, `extract_property_values`, `extract_property_values_as_keys`, `group_by_property`, `to_list`, `to_dicts`; sorters intentionally not ported)

---

## 8. AbstractRequest + validation engine

### Pattern

Request objects validate and normalize all input at the boundary, expose only
whitelisted fields, support PATCH semantics (only-submitted-fields), and produce
structured errors. CloudSale ships a string-DSL validation engine; Warehouse
uses Pydantic.

### CloudSale (PHP)

`requests/AbstractRequest.php` holds a `RULES` map and an `EDITABLE` map. The
constructor copies only fields present in `RULES`, then validates via the engine.
`hasKey($name)` reports whether a field was actually submitted (the PATCH key
check). `__get` refuses access until validated and only for `RULES` fields.

```php
abstract class AbstractRequest {
    const RULES = array();
    const EDITABLE = array();
    public function hasKey($name) { /* throws unless validated; then property_exists */ }
    public function toArray() { return (array)$this->data; }
    public function isValid() { /* lazily validate */ }
    public function getErrors() { return $this->errors; }
    public function validate() {
        $result = $this->Ioc->RequestValidatorInstance->get(static::RULES)->check($this->data);
        // sets isValid + errors
    }
}

class ProductCreateRequest extends \requests\AbstractRequest {
    const RULES = array(
        'name'         => 'string|min_length:1|required',
        'price'        => 'numeric|nonnegative|required',
        'measure_unit' => 'string|in:g,kg,ml,l,pcs|required',
    );
}
class ProductUpdateRequest extends \requests\AbstractRequest {  // PATCH: nothing required
    const RULES = array('name'=>'string|not_empty','price'=>'numeric|nonnegative','measure_unit'=>'string|in:g,kg,ml,l,pcs');
}
```

`infrastructure/RequestValidator.php` is a ~1100-line engine that parses the
pipe-delimited rule DSL (`string|min_length:1|required`) into a per-field rule
set, checks for contradictory rules at parse time, then validates types, ranges,
lengths, counts, dates/datetimes, enums (`in:`), nested requests (`request:`),
arrays (`array`, `min_count`/`max_count`/`unique_values`), and an `expandable:`
mini-grammar for `?expand=recipe[products]` query syntax. Error messages come
from `ValidationErrorDefinitions`.

### Warehouse (Python/FastAPI)

Requests are Pydantic models bound by FastAPI (`app/requests/auth/*.py`):

```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str
```

Mapping of the rule DSL to Pydantic / FastAPI:

| CloudSale rule | Pydantic / FastAPI equivalent |
|---|---|
| `required` | required field (no default) |
| `string` | `str` |
| `int` / `numeric` / `decimal:l,r` | `int` / `float` / `condecimal(max_digits, decimal_places)` |
| `email` | `EmailStr` |
| `url` | `AnyUrl` / `HttpUrl` |
| `min_length` / `max_length` / `length` | `Field(min_length=, max_length=)` / `StringConstraints` |
| `min` / `max` / `range` | `Field(ge=, le=)` |
| `positive` / `negative` / `nonnegative` | `Field(gt=0)` / `Field(lt=0)` / `Field(ge=0)` |
| `in:a,b,c` | `Literal["a","b","c"]` or `Enum` |
| `nullable` | `T | None` |
| `array` + `min_count`/`max_count` | `list[T]` + `Field(min_length=, max_length=)` |
| `unique_values` | validator using `set(...)` length check |
| `not_with` / `required_or` | `model_validator(mode="after")` |
| `datetime`/`date` (ISO + bounds) | `datetime`/`date` + field validator |
| `expandable:` query grammar | custom dependency parsing the `expand` query param |

PATCH semantics:

- CloudSale `hasKey($field)` → Pydantic **`model_fields_set`** (the exact
  `RULES.md` mandate: "PATCH requests validate only submitted fields using
  `model_fields_set`"). For update requests, make all fields `Optional` with no
  default, validate, then iterate `request.model_fields_set` to build the change
  set that feeds `extract_differences` (section 6).
- CloudSale `getErrors()` structured output → FastAPI's `RequestValidationError`
  (422 with a field-error list). For the CloudSale-style single `V001`
  validation envelope, install a custom exception handler that reshapes the 422
  body (section 12).

What exists vs. to build:

- **Built**: per-request Pydantic models, FastAPI boundary validation, the
  container resolving `*Request` to a `GenericFactory` for symmetry.
- **Built**: `app/helpers/expand_validator.py` — `validate_expand(raw,
  expandable) -> dict[str, list[str]]`, the CloudSale `checkExpandable` port
  (REPLACES the earlier `expand.py` parser, which is deleted). Parses
  `?expand=resource[field1,field2],other` AND whitelists it against a
  per-endpoint `expandable` spec `{resource: [allowed_field, ...]}`: rejects
  resources not in the spec, rejects fields not in `expandable[resource]`, and
  expands a bracket-less resource to all `expandable[resource]` fields. `None`/
  empty -> `{}`. Malformed input or any whitelist violation raises
  `RequestValidationError` routed through the unified 422 `V001` envelope.
  `expand_dependency(expandable)` is the FastAPI `Query`-bound dependency factory
  that replaces the old un-whitelisted `expand_param`. Security contract: the
  `expandable` whitelist is the trust boundary — returned names are validated, so
  un-whitelisted resource/field names are rejected (never reflected into
  `getattr`/SQL/dynamic resolution); the empty-bracket "all" path is bounded by
  the spec's declared fields.
- **Built**: `app/main.py` — `RequestValidationError` handler returning
  `{"error": {"code": "V001", "message": ..., "details": [...]}}` with HTTP 422.
  Scoped to `RequestValidationError` only; other exceptions are unaffected.
- **To build**: an `AbstractRequest` base only if shared behaviour is needed
  (e.g. a common `to_change_set()` using `model_fields_set`, or a shared config).
  The validation *engine* is **not** ported — Pydantic replaces it entirely.
- **To build**: PATCH `model_fields_set` workflow per domain.

### Status: **Partial** (Pydantic models + boundary validation + the whitelisting `validate_expand`/`expand_dependency` + unified 422 envelope built; PATCH `model_fields_set` workflow to build per domain)

---

## 9. AbstractError + ErrorDefinitions

### Pattern

Domain errors carry a **unique code**, a message (templated from a central
definitions map), an optional `reference`, `details`, and the HTTP exception
class to raise. Each error knows how to serialize itself and how to throw itself.

### CloudSale (PHP)

```php
abstract class AbstractError implements \JsonSerializable {
    protected $code; protected $message; protected $reference; protected $details;
    protected $exception = 'BadRequest';   // maps to exceptions/ClientErrors/<Name>
    abstract protected function process();  // subclass sets code/message/details/exception
    public function export() {
        // builds {code, message (from ErrorDefinitions[code] if not set), reference:'GE-'.code, details}
    }
    public function throwException() {
        $ex = new ('\exceptions\ClientErrors\'.$this->exception)();
        $ex->setError($this);
        throw $ex;
    }
}

class ProductNameAlreadyExistsError extends \errors\AbstractError {
    protected function process($name = '') {
        $this->code = 'P002';
        $this->message = str_replace('{name}', (string)$name, $this->ErrorDefinitions['P002']);
        $this->details = ['name' => $name];
        $this->exception = 'Conflict';   // → HTTP 409
    }
}
```

`definitions/ErrorDefinitions.php` is the single source of message templates and
unique codes:

```php
return array(
    'A001' => 'The request cannot be processed. You do not have permissions...',
    'P001' => 'Product with product_id {product_id} does not exist.',
    'P002' => 'Product with name {name} already exists.',
    'P003' => 'Product ... cannot be deleted because it is used in recipes.',
    'R001' => 'Recipe with recipe_id {recipe_id} does not exist.',
    'V001' => 'The request contains invalid query or body parameters.',
    // ... unique-coded across the system
);
```

The HTTP exception classes (`exceptions/ClientErrors/{BadRequest,Conflict,
Forbidden,NotFound,Unauthorized}.php`) map error → status code.

### Warehouse (Python/FastAPI)

Current Warehouse errors are bare exception classes with no code, message
template, details, or status mapping:

```python
class InvalidCredentialsError(Exception): pass
class InvalidTokenError(Exception): pass
class ExpiredTokenError(Exception): pass
```

They are constructed via `self.SomeError.get("message")` and caught in the
controller by `self.SomeError.target`, then translated to `HTTPException`
manually inside each route.

To port the CloudSale model, build:

1. **`app/errors/abstract_error.py`** — an `ApplicationError(Exception)` base
   carrying `code: str`, `message: str`, optional `details: dict`,
   `reference: str`, and an HTTP `status_code`. Subclasses set these in `__init__`
   (the Python analogue of `process()`):

   ```python
   class ApplicationError(Exception):
       code: str = "AE00"
       status_code: int = 400
       def __init__(self, message: str | None = None, *, details: dict | None = None) -> None:
           self.message = message or ErrorDefinitions.get(self.code, "Bad Request")
           self.details = details or {}
           self.reference = f"GE-{self.code}"
           super().__init__(self.message)
       def export(self) -> dict:
           out = {"code": self.code, "message": self.message, "reference": self.reference}
           if self.details: out["details"] = self.details
           return out
   ```

   ```python
   class ProductNameAlreadyExistsError(ApplicationError):
       code = "P002"
       status_code = 409
       def __init__(self, name: str) -> None:
           super().__init__(ErrorDefinitions["P002"].format(name=name), details={"name": name})
   ```

2. **`app/errors/error_definitions.py`** (or the container `*Definitions`
   suffix) — the central `ErrorDefinitions: dict[str, str]` map with unique codes
   and `{placeholder}` templates (Python `str.format`, not PHP `str_replace`).

3. **A single FastAPI exception handler** that catches `ApplicationError`,
   reads `status_code`, and returns `{"error": err.export()}` — removing the
   per-route `try/except → HTTPException` boilerplate (section 12).

4. **`ErrorFactory.throw(*args)`** (section 2) so call sites read
   `self.ProductNameAlreadyExistsError.throw(name)` instead of `raise ....get(...)`.

Mapping notes:

- CloudSale's `reference` defaults to `'GE-' . code`; keep the same convention.
- CloudSale chooses the HTTP status via the `$exception` class name; in Warehouse
  put `status_code` directly on the error class — simpler and avoids a parallel
  exception hierarchy.
- The unique-code discipline (`RULES.md`: "Error codes are unique across the
  system") matches CloudSale exactly. Reuse the code namespacing convention
  (letter prefix per domain: `U*` user, `P*` product, `R*` recipe, `A*` auth,
  `V001` validation) adapted to Warehouse domains (warehouses, production, sales,
  inventory).

### Status: **To build** (bare exception classes exist; coded error model, definitions map, central handler, and `throw` helper to build)

---

## 10. TransactionHelper — deadlock-retry wrapper

### Pattern

Controllers wrap every mutation in a transaction boundary. The helper begins a
transaction, runs the callback, commits on success, rolls back on failure, and
**retries on deadlock** with backoff.

### CloudSale (PHP)

```php
public function wrap(callable $function) {
    $this->db->canHandleDeadlock = true;
    $attempts = 10; $sleepBetweenAttemptsMS = 100;
    do {
        try {
            $this->db->trans_start();
            $result = $function();
            if (!$this->db->trans_status()) { throw new \exceptions\DatabaseError(); }
            $this->db->trans_complete();
            $ok = true; break;
        }
        catch (\exceptions\DbDeadlockException $ex) {
            $this->db->trans_set_status(false); $this->db->trans_complete();
            if ($ctr < $attempts) { usleep($sleepBetweenAttemptsMS * 1000); }   // retry
        }
        catch (\Exception $ex) {
            $this->db->trans_set_status(false); $this->db->trans_complete();
            throw $ex;   // non-deadlock: bubble up
        }
    } while (++$ctr <= $attempts);
    if (!$ok) { throw new \exceptions\DatabaseError(); }
    return $result;
}
```

Up to 10 attempts, 100ms between retries, deadlock-only retry, everything else
re-raised.

### Warehouse (Python/FastAPI)

`app/infrastructure/transaction.py` has the commit/rollback boundary but **no
retry loop**:

```python
class TransactionHelper:
    async def wrap(self, session, func, *args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
```

To reach parity, wrap the body in a retry loop that catches only Postgres
serialization/deadlock failures and re-raises everything else:

```python
import asyncio
from sqlalchemy.exc import DBAPIError, OperationalError

_DEADLOCK_SQLSTATES = {"40P01", "40001"}  # deadlock_detected, serialization_failure

async def wrap(self, session, func, *args, attempts=10, backoff_ms=100, **kwargs):
    for attempt in range(1, attempts + 1):
        try:
            result = await func(*args, **kwargs)
            await session.commit()
            return result
        except DBAPIError as exc:
            await session.rollback()
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
            if sqlstate in _DEADLOCK_SQLSTATES and attempt < attempts:
                await asyncio.sleep(backoff_ms / 1000)
                continue
            raise
        except Exception:
            await session.rollback()
            raise
```

Mapping notes:

- CloudSale's MySQL deadlock maps to Postgres SQLSTATE `40P01`
  (`deadlock_detected`) and `40001` (`serialization_failure`, relevant under
  `SERIALIZABLE`/`REPEATABLE READ`). asyncpg surfaces these via the wrapped
  `DBAPIError.orig.sqlstate`.
- The container already exposes `ioc.transaction` (memoized), so controllers
  call `await ioc.transaction.wrap(ioc.session, service_method, ...)` — identical
  ergonomics to CloudSale's `$this->TransactionHelper->wrap(fn)`.
- Keep retry transparent to services: the wrapped callback must be idempotent
  across retries (re-read locked rows inside the callback, do not capture state
  computed before `wrap`).

### Status: **Partial** (commit/rollback boundary built; deadlock retry/backoff to build)

---

## 11. RequestHelper

### Pattern

CloudSale's `RequestHelper` reads raw HTTP input: method, JSON/form body, query
params, URL params, API-key header, and validates JSON.

### CloudSale (PHP)

`helpers/RequestHelper.php` manually parses `$_SERVER`, `php://input`, `$_GET`,
the `HTTP_APIKEY` header, and exposes `getBody()`, `getQuery()`,
`getQueryParam()`, `getMethod()`, `getResource()`, `isApiCall()`, `getApiKey()`.

### Warehouse (Python/FastAPI)

Fully replaced by the framework. FastAPI parses and validates the body into the
Pydantic request model (the parameter typed `body: SomeRequest`), exposes query
params as typed function parameters or `Request.query_params`, headers via
`Header(...)`, and method/path via the route declaration. The API-key concern is
handled by an auth dependency, not a request helper.

No port needed. Do **not** recreate a `RequestHelper` — it would duplicate the
framework and bypass FastAPI validation.

### Status: **Built** (provided by FastAPI/Starlette)

---

## 12. ResponseHelper

### Pattern

CloudSale's `ResponseHelper` centralizes response shaping: `sendData($data)`
wraps payloads as `{ "data": ... }`, `sendPageData(...)` emits paginated bodies,
`sendNoContent()`, and `send{BadRequest,Unauthorized,Forbidden,NotFound,Conflict,
...}` set the status code and emit `{ "error": ... }`.

### CloudSale (PHP)

```php
public function sendData($data) {
    http_response_code(200);
    $response = new \stdClass(); $response->data = $data;
    $this->respond($response); $this->quit(200);
}
public function sendConflict($error) {
    http_response_code(409);
    $response = new \stdClass(); $response->error = $error->export();
    $this->respond($response); $this->quit(409);
}
// respond() sets the X-CloudSale-Version header and json-encodes
```

### Warehouse (Python/FastAPI)

Success responses are the return value of the route (FastAPI serializes it and
sets 200/204). Two CloudSale conventions worth porting:

- **`{ "data": ... }` envelope** — CloudSale wraps all success payloads. Decide a
  Warehouse convention (envelope vs. bare body). If keeping the envelope, use a
  generic Pydantic response wrapper or a small response model rather than
  hand-building dicts. The current auth routes return bare bodies
  (`{"access_token": ...}`), so the envelope is **not** currently applied.
- **`{ "error": err.export() }` for failures** — replace CloudSale's per-call
  `send{Conflict,NotFound,...}` with a **single FastAPI exception handler** on
  `ApplicationError` (section 9):

  ```python
  @app.exception_handler(ApplicationError)
  async def application_error_handler(request: Request, exc: ApplicationError):
      return JSONResponse(status_code=exc.status_code, content={"error": exc.export()})
  ```

  This removes the per-route `try/except → HTTPException` blocks currently in
  `auth/router.py`.

Pagination responses map CloudSale's `PageData`/`PaginationData` (section 13) to
a Pydantic page model `{ "data": [...], "pagination": { "current_page",
"results_per_page", "all_pages" } }`.

Mapping notes:

- `http_response_code()` + `die()` → FastAPI return value or `JSONResponse`.
- The `X-CloudSale-Version` header → a Warehouse version header set via
  middleware if desired (optional).
- `sendNoContent()` → `Response(status_code=204)` (already used in
  `auth/router.py` `logout`).

### Status: **Partial** (framework handles success responses; central error-envelope handler and the success/page envelope convention to build)

---

## 13. Storage query / filter / lock / pagination pattern

### Pattern

A concrete storage exposes `getById`, `getByName`, `get(filters)`,
`getPartial(filters, fields)`, `getPage(filters)`, `create`, `update`, `delete`,
plus a `processFilters` that translates a filter dict into query predicates and
ordering. Reads can take a lock type. Pagination computes total rows.

### CloudSale (PHP)

`storages/ProductStorage.php`:

```php
public function getById($productId, $lockType = false) {
    $this->processLock($lockType);
    $res = $this->db->where('product_id', $productId)->get('products')->result();
    return empty($res) ? false : $this->ProductData->make($res[0]);
}
public function get($filters, $lockType = false) {
    $this->processFilters($filters);
    $this->processLock($lockType);
    return $this->ProductData->makeCollection($this->db->get('products')->result());
}
public function getPage($filters, $lockType = false) {
    $result = $this->PageData->make(['pagination' => $this->processPageFilters($filters)]);
    $this->processFilters($filters);
    $this->processLock($lockType);
    $this->db->setCalcFoundRows(true);
    $result->data = $this->ProductData->makeCollection($this->db->get('products')->result());
    $result->pagination->setResultsCount($this->db->query('SELECT FOUND_ROWS() as ct')->row()->ct);
    return $result;
}
public function create(\data\ProductData $productData) {
    if (!$this->db->insert('products', $productData->toArray())) { throw new \exceptions\DatabaseError(); }
    $productData->product_id = $this->db->insert_id();   // assign PK back
}
public function processFilters($filters) {
    if (!empty($filters['product_ids'])) { $this->db->where_in('product_id', $filters['product_ids']); }
    $this->db->order_by($filters['order_by'] ?? 'product_id');
}
```

### Warehouse (Python/FastAPI)

Port to SQLAlchemy async. Per `RULES.md`, use ORM for CRUD and Core for complex
queries/reporting. Skeleton:

```python
from sqlalchemy import select, insert, update, delete, func

class ProductStorage(AbstractStorage):
    async def get_by_id(self, product_id: str, lock: DbLock | None = None) -> ProductData | None:
        stmt = select(products).where(
            products.c.id == product_id,
            products.c.tenant_id == self.tenant_id,        # tenant scope — Warehouse-only
        )
        stmt = self._apply_lock(stmt, lock)                # .with_for_update() etc.
        row = (await self.session.execute(stmt)).first()
        return ProductData.from_row(row) if row else None

    async def get_page(self, filters: dict, lock: DbLock | None = None) -> Page[ProductData]:
        pagination = self._process_page_filters(filters)   # page/per_page → limit/offset
        stmt = select(products, func.count().over().label("total")).where(products.c.tenant_id == self.tenant_id)
        stmt = self._process_filters(stmt, filters)
        stmt = stmt.limit(pagination.results_per_page).offset(pagination.offset)
        rows = (await self.session.execute(stmt)).all()
        pagination.set_results_count(rows[0].total if rows else 0)
        return Page(data=[ProductData.from_row(r) for r in rows], pagination=pagination)

    async def create(self, data: ProductData) -> None:
        result = await self.session.execute(
            insert(products).values(tenant_id=self.tenant_id, **data.to_dict()).returning(products.c.id)
        )
        data.id = str(result.scalar_one())   # assign PK back — same contract as CloudSale
```

Mapping notes:

- **`FOUND_ROWS()` has no Postgres equivalent.** Use `count(*) OVER ()` as a
  window column on the page query (one round-trip) or a separate `COUNT(*)` with
  the same `WHERE`. Do not copy `setCalcFoundRows`.
- **Locks**: `processLock` → `.with_for_update()` (write) /
  `.with_for_update(read=True)` → emits `FOR SHARE` on Postgres. Define `DbLock`
  enum in `AbstractStorage` (section 5).
- **Tenant predicate is mandatory** on every query — no CloudSale counterpart.
- **PK assignment back to Data** via `RETURNING`.
- `processFilters` becomes a method that mutates/returns a `Select` based on a
  validated filters dict (the filters come from a `*CollectionFilterRequest`
  Pydantic model, mirroring CloudSale's `ProductCollectionFilterRequest`).

### Status: **To build** (no SQL storage exists yet; `RefreshTokenStorage` is Redis-only)

---

## 14. Service orchestration without DB access

### Pattern

Services hold all business logic, coordinate one or more storages, raise coded
errors, and never touch the database or open transactions. The controller wraps
the service call in a transaction.

### CloudSale (PHP)

Create flow: `Products::post()` validates the request, then
`TransactionHelper->wrap(fn)` calls `ProductCreateService->create($request)`,
which checks uniqueness via storage (under write lock), builds Data, persists via
storage, returns Data. Update flow uses `extractDifferences` + `injectInto` for
PATCH semantics. Delete checks referential use (`isUsedInRecipes`) before
deleting.

### Warehouse (Python/FastAPI)

`AuthService` already demonstrates the shape (coordinates `RefreshTokenStorage`,
raises container errors, no DB/transaction control). The full
controller→service→storage→data flow for a SQL-backed domain looks like:

```python
# controller
@router.post("/products")
async def create_product(body: ProductCreateRequest, ctrl: ProductController = Depends(ProductController)):
    return await ctrl.create(body)

class ProductController(BaseController):
    async def create(self, body: ProductCreateRequest) -> dict:
        product = await self.transaction.wrap(self.session, self.ProductCreateService.create, body)
        return product.to_dict()

# service (no DB, no transaction)
class ProductCreateService(AbstractService):
    async def create(self, request: ProductCreateRequest) -> ProductData:
        if await self.ProductStorage.get_by_name(request.name, lock=DbLock.WRITE):
            self.ProductNameAlreadyExistsError.throw(request.name)
        product = ProductData(name=request.name, price=request.price, measure_unit=request.measure_unit)
        await self.ProductStorage.create(product)   # assigns product.id
        return product
```

This is a direct, line-for-line analogue of CloudSale once sections 5, 6, 9 and
13 are built. The auth domain proves the pattern works against Redis storage;
the SQL domains repeat it against `AsyncSession`.

### Status: **Built** (pattern proven in auth; SQL-domain services to follow)

---

## Porting checklist (what to build next, in dependency order)

1. **Error model (section 9)** — `ApplicationError` base, `ErrorDefinitions`
   map, central exception handler, `ErrorFactory.throw`. Unblocks clean error
   handling everywhere and removes per-route `try/except`.
2. **AbstractStorage SQL helpers (section 5)** — `DbLock` enum, lock application,
   field selection, `process_page_filters`, tenant-scoped query base. Plus the
   `Page`/`Pagination` data shapes (CloudSale `PageData`/`PaginationData`).
3. **AbstractData diff/merge (section 6)** — the `AbstractData` base (with
   `FIELDS`/`expanded`/`from_row`/`fix_type`/`to_dict`) is built. Remaining: add
   `extract_differences`/`inject_into` only when a PATCH endpoint needs them,
   paired with Pydantic `model_fields_set`.
4. **TransactionHelper retry (section 10)** — add deadlock/serialization retry
   with backoff.
5. **Response envelope + page model (section 12)** — decide and apply the
   `{data}` / `{error}` conventions; add the `ApplicationError` handler.
6. **First SQL domain (sections 13, 14)** — implement one full vertical
   (controller → request → service → storage → data → errors) for a real
   Warehouse domain (e.g. warehouses or products) to validate the whole stack,
   then replicate.

## Things deliberately NOT ported

- **The string-DSL validation engine** (`RequestValidator.php`) — Pydantic
  replaces it. Only the `expandable` query grammar (now built as
  `validate_expand`, section 8) and the unified validation-error envelope are
  ported.
- **`RequestHelper`** — FastAPI/Starlette handle raw HTTP input.
- **CloudSale `AbstractDataCollection` sorters** — Python `sorted(...)` covers
  them. The rest of the collection (`expand_property`, extract, group) IS ported
  as `DataCollection`, section 7.
- **`DataFactory` via the container** — `from_row` classmethods are the Python
  idiom; add `DataFactory` only if `make/makeCollection` ergonomics are wanted.
- **Parallel HTTP-exception class hierarchy** (`exceptions/ClientErrors/*`) —
  put `status_code` directly on the error class instead.
- **MySQL-isms** — `FOUND_ROWS()`, `LOCK IN SHARE MODE`, `insert_id()` map to
  Postgres `count(*) OVER ()` / `FOR SHARE` / `RETURNING`.

## Multi-tenancy: a Warehouse addition with no CloudSale equivalent

CloudSale is single-tenant. Warehouse adds tenant isolation at every layer
(`RULES.md` "Multi-Tenancy"): every table has `tenant_id`, every storage query
filters by `self.tenant_id` (sourced from JWT claims in `get_ioc`, never from
input), and Postgres RLS is a second enforcement layer. When porting any
CloudSale query, **add the tenant predicate** — none of the CloudSale snippets
above include it.
