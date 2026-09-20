# 6. Phase 1 — Backend Foundation

## Goal

Create a clean FastAPI service with configuration, dependency injection, error handling, and OpenAPI.

## Tasks

Create:

```text
backend/
├── app/
│   ├── core/
│   ├── routes/
│   ├── services/
│   ├── repositories/
│   ├── providers/
│   ├── models/
│   ├── schemas/
│   └── main.py
├── tests/
└── pyproject.toml
```

Implement:

- FastAPI application
- environment settings
- CORS
- request ID middleware
- JSON logging
- health endpoint
- readiness placeholder
- API router structure
- exception handlers
- OpenAPI metadata

## Dependency rules

```text
routes
  -> services
      -> repositories
      -> providers
```

Routes must never call SQL.

Providers must never be instantiated directly inside routes.

## Exit tests

- application starts
- `/health` returns 200
- `/health` does not initialize/query DB
- OpenAPI loads
- request ID is generated
- supplied `X-Request-ID` is preserved

---

# 7. Phase 2 — Database and Repositories

## Goal

Create durable PostgreSQL persistence.

## Tasks

### 7.1 SQLAlchemy/data model

Use UUID IDs and UTC timestamps.

Define category, priority, and status enums.

Define complaint model.

Add DB constraints:

- text minimum 10
- text maximum 2000
- location minimum 3
- location maximum 200
- summary maximum 140

### 7.2 Alembic

Configure migrations.

Create initial migration.

Important:

> No `CREATE TABLE` during application startup.

### 7.3 Repository interface

Implement repository operations such as:

```text
create_complaint
get_complaint
list_complaints
count_complaints
update_status
stats_by_category
stats_by_priority
recent_triage_outcomes
```

All SQL must live here.

### 7.4 Indexes

Create:

```text
(status, priority)
created_at
```

Document the exact queries served by each.

### 7.5 Seed

Implement an idempotent seed command.

Requirements:

- >=30 complaints
- realistic Urdu-influenced English
- multiple categories
- multiple priorities/statuses if useful
- repeat execution creates no duplicates

Use a deterministic external seed identifier or deterministic UUID strategy so repeated runs can detect existing rows.

## Exit criteria

```bash
alembic upgrade head
```

works.

Seed twice.

Verify row count is unchanged after second run.

Restart DB container.

Verify rows remain.

---

# 8. Phase 3 — Complaint Domain and API

## Goal

Implement all core complaint behavior without AI complexity first.

## Domain services

Create:

```text
ComplaintService
StatusService
StatsService
```

Potential responsibility split:

### ComplaintService

- validate/use domain inputs
- invoke triage service
- persist complaint
- invalidate relevant caches through cache abstraction

### StatusService

- own transition table
- validate transition
- update repository

### StatsService

- aggregate stats
- coordinate cache

## State machine

Use an explicit table:

```python
ALLOWED_TRANSITIONS = {
    "open": {"in_progress", "rejected"},
    "in_progress": {"resolved", "rejected"},
    "resolved": set(),
    "rejected": set(),
}
```

Do not implement this as scattered route-level conditionals.

## Endpoints

Implement all complaint endpoints except advanced AI/Redis behavior as placeholders through interfaces.

## Validation errors

Return field-level errors.

## Exit criteria

Tests cover:

- valid complaint creation
- invalid text length
- invalid location
- get existing complaint
- get missing complaint -> 404
- filters
- pagination
- page size >100 rejected
- every valid status transition
- every invalid transition -> 409
- terminal state behavior

---
