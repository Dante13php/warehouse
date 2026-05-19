# CloudSale Python Backend

CloudSale is a warehouse and sales management system built with Python and FastAPI.

## Quick Start

- **New to the project?** Start with `CLAUDE.md` for workflow and architecture guidelines
- **Architecture and coding rules?** Read `.claude/rules/RULES.md`
- **Agent workflow?** Read `.claude/agents/orchestrator.md`
- **Need API specifications?** Check `docs/api/ENDPOINTS.md`

## Key Principles

### Architecture

- Explicit layered structure: Controller → Request → Service → Storage → Data
- FastAPI for routing, Pydantic v2 for request validation, SQLAlchemy for database access
- No repositories, managers, facades, or hidden abstractions
- Pure abstract classes (no DI, DB, HTTP, config inside them)

### Coding Standards

- Python 3.12+ with type hints required on all function signatures
- `snake_case` for files, functions, and variables; `PascalCase` for classes
- Pydantic `BaseModel` for requests; `dataclass` for data objects
- Comments only for non-obvious WHY

### Workflow

- Use Claude's planning system for non-trivial changes
- Present plans and wait for approval before implementation
- Follow all layers appropriately (Controller, Request, Service, Storage, Data, Error)
- Update documentation and seeds when adding new structures

### Database

- Storages are the only layer that accesses the database
- Update `cloudsale_full_seed.sql` for new tables and structures
- Follow explicit business access patterns, not speculative optimization

## Common Tasks

### Planning a Feature

1. Read `CLAUDE.md` for workflow
2. Use Claude's planning mode
3. Present plan and wait for approval
4. Reference relevant capability docs in `docs/capabilities/`

### Implementing a Layer

1. Read `.claude/rules/RULES.md` for layer-specific rules
2. Follow naming conventions (e.g., `ProductService`, `ProductStorage`)
3. Use only established layer kinds (no managers, repositories, facades)

### Adding an Endpoint

1. Reference `docs/api/ENDPOINTS.md` for response conventions
2. Update API docs with the new endpoint
3. If adding new tables: update `cloudsale_full_seed.sql`
4. If adding a new capability: create a capability doc in `docs/capabilities/`

## Source Code Organization

```
app/
├── controllers/
│   ├── products/
│   ├── recipes/
│   ├── bills/
│   └── users/
├── requests/
│   ├── product/
│   ├── recipe/
│   ├── bill/
│   └── user/
├── services/
│   ├── product/
│   ├── recipe/
│   ├── bill/
│   └── user/
├── storages/
│   ├── product_storage.py
│   ├── recipe_storage.py
│   ├── bill_storage.py
│   └── user_storage.py
├── data/
│   ├── product_data.py
│   ├── recipe_data.py
│   ├── bill_data.py
│   └── user_data.py
├── errors/
│   ├── product/
│   ├── recipe/
│   ├── bill/
│   └── user/
├── helpers/
└── infrastructure/
main.py
```
