# Full CloudSale-Identical Expand Infrastructure (AbstractData + DataCollection + expand validation)

## Status

`implemented`

## What was built

- **`app/data/abstract_data.py`** — `AbstractData` base mixin: `FIELDS: ClassVar`
  whitelist; type tokens `INT`/`FLOAT`/`STRING`/`BOOL`/`DATETIME`/`EXPANDED`
  (module constants) + `ExpandedField` alias; `from_row` classmethod (maps
  `FIELDS`, applies `fix_type`, defaults `expanded` fields to `[]`, reads
  mapping or attribute rows); `fix_type` (None passthrough, primitive casts,
  datetime -> tz-aware UTC, expanded/unknown passthrough); `__setattr__` field
  guard (rejects names not in `FIELDS`, allows leading-underscore/dunder);
  `to_dict()` in `FIELDS` order.
- **`app/data/data_collection.py`** — `DataCollection[T]` (`TypeVar` bound to
  `AbstractData`): `__init__(items=None)` (no mutable default), `add`,
  `__iter__`/`__len__`/`__getitem__`/`__bool__`, `expand_property`,
  `extract_property_values`, `extract_property_values_as_keys`,
  `group_by_property`, `to_list`, `to_dicts`. Includes a usage docstring.
- **`app/helpers/expand_validator.py`** — `validate_expand(raw, expandable) ->
  dict[str, list[str]]` (CloudSale `checkExpandable` port: bracket-aware grammar
  reused from the deleted parser, whitelist by resource + per-resource fields,
  bracket-less resource -> all allowed fields, `{}` for None/empty, raises
  `RequestValidationError` -> unified `V001` 422 envelope on any violation) +
  `expand_dependency(expandable)` FastAPI dependency factory.
- **`app/helpers/expand.py`** — deleted (the un-whitelisted `parse_expand` /
  `ExpandSpec` / `expand_param` parser). No `app/` references remained.
- **`app/data/auth_user.py`** — kept a plain `@dataclass`; added a comment
  documenting why auth identity data does not extend `AbstractData`
  (no expanded fields; `password_hash` must not be serialized via `to_dict`).
- **Docs** — `CLOUDSALE_PATTERNS.md` §6/§7 reversed to **Built**, §8 expand
  entry + status table + "NOT ported" + §1 helper note + porting checklist
  updated; `RULES.md` documents `AbstractData`, `DataCollection`, the expand
  pattern, and folder structure; `.claude/skills/backend-endpoints/`
  `relations.md` + `layers.md` updated.

### Verification performed

- `python -c "import app.main"` imports cleanly (via `.venv`).
- Acceptance criterion 7 round-trips all pass (`products[name],supplier`,
  bracket-less `products`, `None`, unknown-resource raise, unknown-field raise,
  unbalanced-bracket raise) plus `expand_dependency` factory.
- `AbstractData` checks: `from_row` int/datetime coercion + `expanded` -> `[]`,
  `fix_type` passthrough, field guard rejects unknown setattr, `to_dict` order.
- `DataCollection` checks: `expand_property` (incl. missing-key -> `[]`),
  extract/group utilities, sequence protocol, guard on misnamed expand target.
- Auth unaffected: auth modules import; `AuthUser`/`TokenData` construct;
  `AuthUser` has no `to_dict` (no credential-leak surface).

## Source task or spec

User chose **Option B**: delete the current `app/helpers/expand.py` and build the
full three-level CloudSale-identical expand pattern in Warehouse, even though no
domain entity consumes it yet. The goal is a ready foundation every future entity
will use. This reverses the prior recommendation in
`docs/architecture/CLOUDSALE_PATTERNS.md` §6-8, which currently advises AGAINST
these subsystems (status "Partial"/"To build" with explicit "do not build the
heavyweight class" notes).

The three CloudSale layers being ported (exact behavior, from the brief):

1. **RequestValidator `expandable:` rule** — validates an expand string against a
   per-resource whitelist of allowed resources and (optionally) per-resource
   field whitelists. Empty field list = all allowed fields. Produces a
   `dict[resource -> list[field]]`.
2. **AbstractData `expanded` type in FIELDS** — a `FIELDS` map declares each
   field's type; the `expanded` type marks fields that hold list/array values
   (nested children), passed through as-is by type coercion.
3. **AbstractDataCollection `expand_property()`** — a typed wrapper around
   `list[Data]` that attaches grouped child values onto each parent item by a
   group key, plus the CloudSale collection utilities (`extractPropertyValues`,
   `extractPropertyValuesAsKeys`, group-by).

### CloudSale reference behavior (do not re-design)

**RequestValidator — `expandable:` rule:**
```php
// RULE: 'expand' => 'expandable:recipe_ids[bill_id,price],products'
// checkExpandable():
//   - validates resource names against the whitelist in the rule
//   - validates field names against the per-resource field whitelist (if given)
//   - empty field list = all allowed fields for that resource
// After validation: $request->expand = ['recipe_ids' => ['bill_id','price'], 'products' => [...all...]]
```

**AbstractData — `expanded` type:**
```php
const FIELDS = ['recipe_ids' => 'expanded', 'bill_id' => 'int', ...];
// 'expanded' fields hold list values; fixType() returns the value as-is.
```

**AbstractDataCollection — `expand_property()`:**
```php
public function expandProperty($expandedProperty, $groupKeyProperty, $groupedValues) {
    foreach ($this->collection as $item) {
        $item->$expandedProperty = $groupedValues[$item->$groupKeyProperty] ?? [];
    }
}
```

**Service usage pattern:**
```php
if (isset($requestData->expand['recipe_ids'])) {
    $related = $this->RelatedStorage->getByIds($ids);
    $grouped = /* group by FK */;
    $collection->expandProperty('recipe_ids', 'bill_id', $grouped);
}
```

### Current Warehouse state (commit a32c166 / present worktree)

- `app/helpers/expand.py` exists: `ExpandSpec` (frozen dataclass `resource` +
  `fields` tuple), `parse_expand(raw) -> dict[str, ExpandSpec]` (pure parser,
  brackets-aware), `expand_param` FastAPI `Query` dependency. It is a **parser
  only** — no whitelisting against a resource/field spec. Malformed input raises
  `RequestValidationError` routed through the unified 422 envelope.
- Grep confirms **zero call sites in `app/`** outside the file itself. References
  exist only in docs and skills:
  `docs/plans/2026-05-20-mapper-layer-and-request-patterns.md`,
  `docs/architecture/CLOUDSALE_PATTERNS.md`,
  `.claude/skills/backend-endpoints/references/relations.md`,
  `.claude/skills/javascript/references/motion.md` (unrelated — Motion library,
  not the expand feature).
- Data classes are plain `@dataclass` + `from_row` classmethod
  (`app/data/auth_user.py`, `app/data/token.py`). No `AbstractData`, no `FIELDS`
  map, no type coercion, no field whitelist.
- Storages return single Data or `None`; no collection wrapper. `list[Data]` is
  the implicit collection type. No `AbstractDataCollection`.
- `app/main.py` registers a `RequestValidationError` handler producing the
  `{"error": {"code": "V001", ...}}` envelope (built by the mapper-layer task).

## Confirmed user decisions (do not re-ask)

1. **Build the full three-level expand infrastructure now**, even without a
   domain entity consumer yet. Ready foundation for every future entity.
2. **Delete `app/helpers/expand.py` entirely** (zero `app/` call sites). Remove
   all references to `expand_param`, `ExpandSpec`, `parse_expand` from the
   codebase.
3. **Pydantic stays** for HTTP body validation. The ported "RequestValidator"
   is ONLY the expand-string parsing/whitelisting — NOT a replacement for
   Pydantic. Concretely: a `validate_expand(raw, expandable_spec)` function
   mirroring CloudSale `checkExpandable`.
4. **Data stays as `@dataclass`.** `expanded` is a sentinel type/marker
   recognized by `AbstractData` or a helper — not a behavioral change to how
   dataclasses store fields.
5. **`DataCollection` wraps `list[Data]`** and adds `expand_property()` plus the
   CloudSale `AbstractDataCollection` utilities (extract property values, extract
   as keys, group by property).
6. **docs-writer must REVERSE** `CLOUDSALE_PATTERNS.md` §6-8 to mark these
   patterns as IMPLEMENTED (status **Built**), and update `RULES.md` to document
   `AbstractData`, `DataCollection`, and the expand pattern. Update skill files
   if they reference expand.
7. Workflow: planner → implementer → reviewer → docs-writer → version-control.
   **Stop after planner for approval.** (security agent is added — see Agent
   decisions, R-EXPAND.)

## Python design constraints (from the brief)

- `AbstractData` is a base/mixin for `@dataclass` Data classes. It carries a
  `FIELDS: dict[str, str]` map (field name -> type token), a `from_row` factory,
  and field guards. The `expanded` type token marks list/array fields. The PHP
  magic `__get`/`__set` whitelist is reproduced as field guards that reject
  unknown field names, but field STORAGE remains the dataclass mechanism (no
  `self._` shadow object).
- `DataCollection[T]` is a generic typed wrapper around `list[T]` (T bound to
  `AbstractData`) implementing iteration, length, indexing, plus
  `expand_property()`, `extract_property_values()`,
  `extract_property_values_as_keys()`, `group_by_property()`.
- `validate_expand(raw: str | None, expandable: dict[str, list[str]]) ->
  dict[str, list[str]]` — parses the raw expand string and whitelists it against
  the `expandable` spec (resource names + per-resource field whitelists; empty
  field list in the request = all allowed fields). Mirrors CloudSale's
  `checkExpandable`. Lives in the request/validation layer.

## Scope

### Part A — Delete the old parser

#### A1. Delete `app/helpers/expand.py`

- Remove the file entirely.
- Remove all references to `expand_param`, `ExpandSpec`, `parse_expand` across
  the codebase. (Grep-confirmed: no `app/` imports; only docs/skills mention the
  names — those are handled by docs-writer in Part E, except any that are code.)
- Verify no import in `app/` breaks (`python -c "import app.main"` clean).

### Part B — AbstractData base with `expanded` type marker

#### B1. `app/data/abstract_data.py` — `AbstractData`

A base class for `@dataclass` Data classes providing the CloudSale `FIELDS` /
`expanded` semantics adapted to Python dataclasses.

Design:

- **`FIELDS: ClassVar[dict[str, str]]`** — subclass declares
  `{field_name: type_token}`. Type tokens mirror CloudSale: `"int"`, `"float"`,
  `"string"`, `"bool"`, `"datetime"`, and the new `"expanded"`. `FIELDS` is the
  authoritative field whitelist and the source for type coercion.
- **`EXPANDED` type token constant** — a module-level string sentinel
  (`EXPANDED = "expanded"`) used in `FIELDS` to mark list-valued nested fields.
  Implementer may also expose a typing alias `ExpandedField = list[Any]` for
  annotating the dataclass field, but the load-bearing marker is the `FIELDS`
  entry, matching CloudSale.
- **`from_row(cls, row) -> Self`** — `@classmethod` factory. Default
  implementation maps `FIELDS` keys from the row and applies `fix_type` per
  field. `expanded` fields are NOT read from the row (they are populated later by
  `DataCollection.expand_property`); they default to an empty list. Subclasses may
  override `from_row` for custom mapping (the existing `AuthUser.from_row` style
  stays valid).
- **`fix_type(type_token, value) -> Any`** — per-field coercion mirroring
  CloudSale `fixType`: `int`/`float`/`str`/`bool` cast; `datetime` parse;
  `expanded` returns the value as-is (CloudSale: list passthrough); unknown token
  returns value unchanged. Static/class method.
- **Field guards** — reject reads/writes of names not in `FIELDS`. Because Data
  classes are dataclasses, the guard is implemented as a `__setattr__` (and
  optionally `__getattr__`) check against `FIELDS` so unknown fields raise
  (CloudSale `__get`/`__set` `DomainException` analogue). Implementer must ensure
  the guard does not break dataclass `__init__` (which sets declared fields) and
  does not recurse — leading-underscore / declared-field allowance, same
  discipline as the IoC base classes' `__getattr__` guard. If the guard proves to
  fight dataclass internals, fall back to: dataclass already restricts fields at
  construction, and the guard only covers post-construction dynamic
  `setattr(expanded_field, ...)` — implementer documents the chosen mechanism.
- **`to_dict() -> dict[str, Any]`** — return the field map (for response shaping
  and storage `insert(...).values(...)`). Honors `FIELDS` ordering.
- No business logic beyond field/type plumbing (RULES: Data has no logic beyond
  `__init__`/`from_row`; `to_dict`/`fix_type` are field plumbing, not business
  logic — documented as the agreed exception, consistent with
  CloudSALE_PATTERNS §6 `to_dict` recommendation).

Subclass shape (illustrative — NOT created in this task, no domain entity yet):
```python
@dataclass
class RecipeData(AbstractData):
    FIELDS = {"id": "int", "name": "string", "products": "expanded"}
    id: int
    name: str
    products: list[Any] = field(default_factory=list)
```

#### B2. `app/data/auth_user.py` — extend `AbstractData` if appropriate, else document

Decision rule for the implementer:

- `AuthUser` does not need `expanded` fields, type coercion (its `from_row`
  already casts), or response serialization (it carries a `password_hash` that
  must never be serialized). Extending `AbstractData` adds a `FIELDS` map and a
  field guard with no current benefit and a serialization-leak risk.
- **Default: keep `AuthUser` a plain `@dataclass`** and add a one-line comment /
  short docstring noting that auth identity data stays a plain dataclass (no
  expand fields; `password_hash` must not be serialized via `to_dict`). This
  satisfies the brief's "or document why auth data stays plain dataclass."
- `TokenData` likewise stays a plain dataclass (claims carrier, not an entity).

The brief allows either; the plan selects "document why it stays plain" as the
defensible minimal choice. Implementer may convert `AuthUser` to `AbstractData`
ONLY if it can be done without exposing `password_hash` in `to_dict` and without
breaking `AuthService` — otherwise keep plain + comment.

### Part C — DataCollection wrapper

#### C1. `app/data/data_collection.py` — `DataCollection[T]`

A generic typed wrapper around `list[T]` (`T = TypeVar("T", bound=AbstractData)`)
porting CloudSale `AbstractDataCollection`. Note filename: the brief specifies
`data_collection.py` (CLOUDSALE_PATTERNS §7 referenced `abstract_data_collection.py`;
the brief's `data_collection.py` is authoritative for this task).

Methods:

- **construction** — `DataCollection(items: list[T] | None = None)` (no mutable
  default; default to `[]` inside). `add(item: T) -> None`.
- **sequence protocol** — `__iter__`, `__len__`, `__getitem__`, `__bool__` so it
  behaves like a list where needed.
- **`expand_property(expanded_property: str, group_key_property: str,
  grouped_values: dict[Any, list]) -> None`** — for each item, set
  `item.<expanded_property> = grouped_values.get(item.<group_key_property>, [])`.
  Direct port of CloudSale `expandProperty`. Uses `setattr`/`getattr` — relies on
  `AbstractData`'s field guard to reject a misnamed `expanded_property` (the
  field must be declared `expanded` in `FIELDS`).
- **`extract_property_values(property_name: str) -> list[Any]`** — `[getattr(i,
  property_name) for i in items]` (CloudSale `extractPropertyValues`).
- **`extract_property_values_as_keys(property_name: str) -> dict[Any, T]`** —
  `{getattr(i, property_name): i for i in items}` (CloudSale
  `extractPropertyValuesAsKeys`).
- **`group_by_property(property_name: str) -> dict[Any, list[T]]`** — group items
  into lists keyed by the property (CloudSale
  `toArrayGroupedByPropertyValuesAsKeys`). Used to build the `grouped_values`
  argument for `expand_property` on a CHILD collection before attaching to a
  PARENT collection.
- **`to_list() -> list[T]`** / **`to_dicts() -> list[dict]`** — plain list and
  serialized list (calls `item.to_dict()`), for response shaping.

Sorters from CloudSale (`sortByIntegerPropertyValueAscending`, string sorters)
are **out of scope** — Python `sorted(collection, key=...)` covers them; do not
port. (Documented in Out of scope.)

### Part D — Expand validation (RequestValidator `expandable:` port)

#### D1. `app/helpers/expand_validator.py` — `validate_expand`

The CloudSale `checkExpandable` port. Pure function, no FastAPI coupling in the
core (a thin FastAPI dependency may wrap it — see D2).

Signature:
```python
def validate_expand(
    raw: str | None,
    expandable: dict[str, list[str]],
) -> dict[str, list[str]]: ...
```

Behavior (mirrors CloudSale exactly):

1. `raw` is the user expand string: `resource[f1,f2],other`. `None`/empty -> `{}`.
2. `expandable` is the per-endpoint whitelist: `{resource: [allowed_field, ...]}`.
   An empty allowed-field list for a resource means "all fields allowed" — but in
   Python the caller must supply the concrete allowed field names (there is no
   ambient FIELDS at the validator); so the contract is: `expandable[resource]`
   lists the allowed field names; an EMPTY request field list (`resource` with no
   `[...]`) expands to ALL `expandable[resource]` fields.
3. Parse with the existing bracket-aware grammar logic (reuse the proven parsing
   from the deleted `expand.py` — depth tracking for `[]`, `_NAME_RE` validation
   — but the OUTPUT is the validated `dict[str, list[str]]`, not `ExpandSpec`).
4. Validation:
   - Each requested resource MUST be a key in `expandable`, else raise.
   - Each requested field MUST be in `expandable[resource]`, else raise.
   - A resource requested with no `[...]` -> all of `expandable[resource]`.
5. On any violation, raise `RequestValidationError` so it routes through the
   existing unified 422 `V001` envelope (same mechanism the deleted `expand.py`
   used via `_raise_validation_error`). Reuse / re-home that error-raising helper.
6. Return `{resource: [field, ...]}` — the structure CloudSale stores on
   `$request->expand` and services consume via `if 'recipe_ids' in request.expand`.

Security contract (carried over from the deleted file's header): the returned
resource/field names are validated against the `expandable` whitelist, so they
are safe to use as response keys and as a basis for which child storages to call.
They MUST still not be passed raw into `getattr(ioc, ...)` or SQL identifiers
without the whitelist (the whitelist IS the validation here). Document this.

#### D2. Request-layer integration point

- The brief allows "(or integrate into request layer)". Decision: keep the
  validator as `app/helpers/expand_validator.py` (pure, unit-testable, no
  FastAPI), AND provide a small reusable dependency factory so controllers/
  collection-filter requests can declare their `expandable` spec:
  ```python
  def expand_dependency(expandable: dict[str, list[str]]):
      def _dep(expand: str | None = Query(default=None)) -> dict[str, list[str]]:
          return validate_expand(expand, expandable)
      return _dep
  ```
  Placement of `expand_dependency`: alongside the validator in
  `app/helpers/expand_validator.py`. This is the replacement for the deleted
  `expand_param` (which had no whitelist). It is wired by future endpoints; no
  endpoint wires it in this task (no domain entity yet).
- Helpers stay plain importable modules (existing convention; no `*Helper` IoC
  suffix).

### Part E — Documentation (docs-writer, after review)

- **`docs/architecture/CLOUDSALE_PATTERNS.md`** — REVERSE §6, §7, §8 expand
  recommendations:
  - §6 (AbstractData): status **Partial -> Built**. Replace the "keep per-entity
    dataclass, only add a mixin if PATCH-diff needed, do NOT reproduce magic
    `__get`/`__set`" recommendation with the as-built `AbstractData` (FIELDS,
    `expanded` token, `from_row`, `fix_type`, field guard, `to_dict`).
  - §7 (AbstractDataCollection): status **To build -> Built**. Replace the "do
    NOT introduce a heavyweight AbstractDataCollection, prefer comprehensions"
    recommendation with the as-built `DataCollection` (`expand_property`,
    `extract_property_values`, `extract_property_values_as_keys`,
    `group_by_property`, `to_dicts`). Note filename `app/data/data_collection.py`.
  - §8 (AbstractRequest + validation engine): keep "validation engine NOT ported"
    but update the expand entry: the old built `expand.py` parser is REPLACED by
    the whitelisting `validate_expand` (`app/helpers/expand_validator.py`).
    Update the status-summary table rows 6, 7 to **Built** and row 8's expand
    note. Update the "Things deliberately NOT ported" section to remove the
    "heavyweight AbstractDataCollection" exclusion and adjust the AbstractData
    note.
  - §1's note listing helpers includes `expand.py` — update to
    `expand_validator.py`.
  - Update the "Porting checklist" item 3 (AbstractData diff/merge) to reflect
    the now-built base (diff/merge `extract_differences`/`inject_into` remain
    out of scope unless PATCH lands — note that).
- **`.claude/rules/RULES.md`** — document the new patterns:
  - Data layer rules: add `AbstractData` base, `FIELDS` map with type tokens
    including `expanded`, `fix_type`, `to_dict`, field guard.
  - Add a `DataCollection` description (wraps `list[Data]`, expand/group/extract
    utilities) — decide section (Data, or a new "Collections" note under Data).
  - Document the expand pattern: `validate_expand` whitelisting, the
    request-layer dependency, the service usage pattern
    (`if resource in request.expand: load children, group, expand_property`).
  - Folder structure: `app/data/abstract_data.py`, `app/data/data_collection.py`,
    `app/helpers/expand_validator.py` are part of the structure.
- **`.claude/skills/backend-endpoints/`** — update files referencing expand:
  - `references/relations.md` — the "Treat `expand` as collection-only behavior"
    rule stays, but update any mechanics to reference `validate_expand` /
    `expand_dependency` + `expandable` spec and the `DataCollection.expand_property`
    service pattern.
  - `SKILL.md` / other references — add the AbstractData/DataCollection/expand
    pattern to the layer guidance if expand is mentioned.
- **This plan file** -> `implemented` with a "What was built" section.

## Out of scope

- Any concrete domain entity, endpoint, storage, service, or `*Data` subclass.
  This task builds the FOUNDATION only; no consumer is wired.
- CloudSale `AbstractData` diff/merge (`extract_differences`, `inject_into`) and
  the PATCH `model_fields_set` workflow — separate pattern (§6 follow-up), only
  when an update endpoint needs it.
- CloudSale `AbstractDataCollection` sorters — Python `sorted(...)` covers them.
- `DataFactory` / container `*Data` suffix wiring — `from_row` stays the idiom;
  not wired into IoC.
- The full coded-error model (`ApplicationError`/`ErrorDefinitions`, pattern §9).
  Expand validation errors route through the EXISTING `V001` 422 envelope only.
- The `{"data": ...}` success envelope and page models (pattern §12).
- Database schema / migrations / seed SQL — no table changes (no entity).
- Frontend / UI — none.
- Multi-level/recursive expand (expand within expand) — single-level
  parent->children only, matching the CloudSale `expandProperty` semantics.

## Acceptance criteria

1. `app/helpers/expand.py` is deleted. Grep for `parse_expand`, `ExpandSpec`,
   `expand_param` returns ZERO matches in `app/` (docs/skills updated separately
   by docs-writer; the unrelated `motion.md` "expand" hit is not this feature).
2. `app/data/abstract_data.py` exists: `AbstractData` with `FIELDS: ClassVar`
   field whitelist, an `EXPANDED` (`"expanded"`) type token, `from_row`
   classmethod, `fix_type` coercion (int/float/str/bool/datetime/expanded
   passthrough), field guard rejecting unknown field names, and `to_dict()`.
3. `expanded` fields are NOT read from the DB row by the default `from_row` and
   default to an empty list; `fix_type("expanded", v)` returns `v` unchanged.
4. `app/data/data_collection.py` exists: generic `DataCollection[T]` wrapping
   `list[T]` with `__iter__`/`__len__`/`__getitem__`/`__bool__`, `add`,
   `expand_property(expanded_property, group_key_property, grouped_values)`,
   `extract_property_values`, `extract_property_values_as_keys`,
   `group_by_property`, `to_list`, `to_dicts`. No mutable default arguments.
5. `expand_property` sets `item.<expanded_property> =
   grouped_values.get(item.<group_key_property>, [])` for every item — matches
   CloudSale semantics (missing key -> empty list).
6. `app/helpers/expand_validator.py` exists: `validate_expand(raw, expandable)
   -> dict[str, list[str]]` that (a) parses `resource[f1,f2],other`, (b) rejects
   resources not in `expandable`, (c) rejects fields not in
   `expandable[resource]`, (d) expands a bracket-less resource to all
   `expandable[resource]` fields, (e) raises `RequestValidationError` (routed
   through the existing `V001` 422 envelope) on any violation, (f) returns `{}`
   for `None`/empty input. Plus an `expand_dependency(expandable)` factory
   returning a FastAPI `Query`-bound dependency.
7. A round-trip check: with `expandable = {"products": ["id","name"],
   "supplier": ["id"]}`, `validate_expand("products[name],supplier", expandable)`
   == `{"products": ["name"], "supplier": ["id"]}`; `validate_expand("products",
   expandable)` == `{"products": ["id","name"]}`; `validate_expand("unknown",
   expandable)` raises; `validate_expand("products[price]", expandable)` raises;
   `validate_expand(None, expandable)` == `{}`.
8. `AuthUser` either extends `AbstractData` without exposing `password_hash` via
   `to_dict`, OR remains a plain `@dataclass` with a comment explaining why auth
   data stays plain. `AuthService` and existing auth flows are unaffected.
9. `python -c "import app.main"` imports cleanly; existing auth flows unchanged
   (invalid login body -> enveloped 422, `/auth/refresh` unknown -> 401,
   `/auth/logout` -> 204).
10. All new/changed code: full type hints, `logging` not `print`, no mutable
    default args, layer boundaries respected, files `snake_case`, classes
    `PascalCase`. `DataCollection` uses `TypeVar` bound to `AbstractData`.
11. Docs reversed/updated: `CLOUDSALE_PATTERNS.md` §6/§7 status -> **Built** and
    §8 expand note + status table + "NOT ported" section corrected; `RULES.md`
    documents `AbstractData`, `DataCollection`, expand pattern + folder structure;
    `.claude/skills/backend-endpoints/` files that mention expand updated.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/helpers/expand.py` | deleted | implementer |
| `app/data/abstract_data.py` | created (`AbstractData` + `EXPANDED` token) | implementer |
| `app/data/data_collection.py` | created (`DataCollection[T]`) | implementer |
| `app/helpers/expand_validator.py` | created (`validate_expand` + `expand_dependency`) | implementer |
| `app/data/auth_user.py` | updated (extend `AbstractData` or add "stays plain" comment) | implementer |
| (codebase) | remove any `app/` references to `parse_expand`/`ExpandSpec`/`expand_param` (grep-confirmed none today) | implementer |
| `docs/architecture/CLOUDSALE_PATTERNS.md` | updated (REVERSE §6/§7/§8, status table, "NOT ported", §1 note) | docs-writer |
| `.claude/rules/RULES.md` | updated (`AbstractData`, `DataCollection`, expand pattern, folder structure) | docs-writer |
| `.claude/skills/backend-endpoints/references/relations.md` | updated (expand mechanics) | docs-writer |
| `.claude/skills/backend-endpoints/SKILL.md` (+ other references if they mention expand) | updated if applicable | docs-writer |
| `docs/plans/2026-05-20-expand-infrastructure-abstract-data-collection.md` | this plan -> `implemented` at end | docs-writer |

## Risks

- **R1 — `AbstractData` field guard vs. dataclass internals.** A `__setattr__`/
  `__getattr__` guard can fight dataclass `__init__` (which sets declared fields)
  and `field(default_factory=...)`, and risks recursion. Mitigation: the guard
  allows all names in `FIELDS` (plus leading-underscore/dunder), and dataclass
  construction only sets declared fields. Implementer must verify dataclass
  `__init__`, defaults, and `expand_property`'s `setattr` all work. If the guard
  proves brittle, fall back to "dataclass restricts fields at construction; guard
  covers only post-construction dynamic sets" and document. Reviewer verifies.
- **R2 — `expanded` field default & serialization.** Expanded fields must default
  to `[]` (not shared mutable default) — use `field(default_factory=list)` in
  subclasses; `AbstractData.from_row` must not crash when the row lacks the
  expanded column. `to_dict()` must include expanded fields as their list value.
  Reviewer verifies no mutable-default sharing.
- **R3 — `validate_expand` security surface.** `?expand=` is user input. The
  whitelist (`expandable`) is the trust boundary; resource/field names not in it
  must be rejected, never reflected into `getattr`/SQL. The empty-bracket =
  "all allowed" path must expand to the SPEC's fields, never to arbitrary input.
  Mitigation: validation rejects unknown resources/fields before return; security
  agent reviews. (R-EXPAND below.)
- **R4 — Reusing the deleted parser's grammar correctly.** The bracket-depth
  parsing and `_NAME_RE` from `expand.py` are proven; porting them into
  `validate_expand` must preserve unbalanced-bracket handling and the
  `RequestValidationError` routing. Mitigation: reuse the exact parsing logic and
  the `_raise_validation_error` mechanism; acceptance criterion 7 covers
  round-trips and rejection.
- **R5 — Deleting `expand.py` breaks an import.** Grep shows no `app/` importers,
  but a hidden dynamic import could exist. Mitigation: `python -c "import
  app.main"` + grep after deletion (criterion 1, 9).
- **R6 — `DataCollection` generic typing.** `TypeVar` bound to `AbstractData`
  plus `Generic[T]` and the sequence dunders must type-check and behave. Risk of
  over-engineering. Mitigation: keep methods thin (comprehensions); reviewer
  checks it stays a wrapper, not a framework.
- **R7 — Doc reversal drift.** §6-8 reversal must match what was actually built
  (filename `data_collection.py`, validator name, method names). Mitigation:
  docs-writer reads the implemented files, not the brief, before reversing
  (docs-writer rule: document actual behavior). Reviewer flags doc gaps.
- **R8 — No consumer = untested integration.** Building infra with no endpoint
  means the parent->children expand flow is exercised only by the acceptance
  round-trips, not a real query. Accepted by the user (foundation-first). Mitigate
  by making acceptance criterion 7's round-trip exhaustive and adding a docstring
  usage example in `data_collection.py`.

## Agent decisions

- **planner:** this plan, no code. Brainstorming bypassed — the user supplied
  Option B with confirmed decisions, exact CloudSale reference behavior, Python
  design constraints, explicit deliverables, and explicit in/out of scope. No
  open design questions block planning. The one judgment call (`AuthUser` extends
  `AbstractData` vs. stays plain) is resolved with a default + a documented
  fallback rule for the implementer.
- **ui-designer:** not required (no UI scope).
- **database:** not required (no schema/migration/seed change — no domain entity,
  no table).
- **implementer:** owns all code files in the impacted-files table. Build order:
  (1) `AbstractData` (B1) — foundation everything else references; (2)
  `DataCollection` (C1) — depends on `AbstractData`; (3) `validate_expand` +
  `expand_dependency` (D1/D2) — reuse the deleted parser's grammar logic and
  `RequestValidationError` routing; (4) delete `expand.py` (A1) and remove any
  references; (5) `AuthUser` decision (B2). Delete LAST so the grammar logic can
  be copied from it first, then removed.
- **reviewer:** verify field guard does not break dataclass init/defaults (R1);
  expanded-field default is `[]` via `default_factory`, `from_row` tolerant, no
  mutable-default sharing (R2); `validate_expand` rejects unknown
  resources/fields and the empty-bracket path expands to spec fields only (R3);
  grammar/`RequestValidationError` routing preserved (R4); `expand.py` deletion
  leaves no broken imports (R5); `DataCollection` stays a thin typed wrapper (R6);
  type hints / logging / no mutable defaults / naming / layer boundaries
  (criterion 10). Identify doc gaps for docs-writer.
- **security:** **required** (R-EXPAND) — review `validate_expand` as the
  user-input trust boundary: confirm there is NO path from `?expand=` into
  `getattr(ioc, ...)`, dynamic class resolution, or SQL identifiers without the
  `expandable` whitelist; confirm unknown resources/fields are rejected (not
  reflected) and the empty-bracket "all" path is bounded by the spec; confirm the
  documented security contract in the helper matches behavior. Runs after
  reviewer, before docs-writer.
- **docs-writer:** REVERSE `CLOUDSALE_PATTERNS.md` §6/§7/§8 to **Built** matching
  the as-implemented files; update `RULES.md` (`AbstractData`, `DataCollection`,
  expand pattern, folder structure); update `.claude/skills/backend-endpoints/`
  files mentioning expand; set this plan to `implemented` with a "What was built"
  section. Reads the implemented files, not the brief.
- **version-control:** commit plan + code + docs + skill updates together in the
  final commit set at the end. No merge unless requested.

## Approval log

- 2026-05-20: plan drafted (`draft`), awaiting user approval. Brainstorming
  bypassed — user provided Option B with confirmed decisions and exact CloudSale
  reference behavior; design is fully specified. One judgment call (`AuthUser`
  base class) resolved with a default + documented implementer fallback. Security
  agent added (expand is a user-input surface). Approve to proceed to implementer.
