> Moved out of `CivicPulse_ImplementationPlan.md` (formerly §27.1). Graphify is optional
> tooling; the implementation plan remains the authoritative requirements document.

# Graphify — Repository Knowledge Graph for Agents

Graphify is an optional repository-understanding tool for CivicPulse agents. It should be used to **map and query the existing codebase, documentation, configuration, and related artifacts before making changes**. It is not the assignment specification, task tracker, architecture authority, or a replacement for reading `CivicPulse_ImplementationPlan.md`.

Graphify's repository provides a `/graphify` skill for AI coding assistants including Codex. It builds a queryable knowledge graph from the project, with local deterministic AST parsing for code and explainable `EXTRACTED` versus `INFERRED` relationships. It is a graph, not a vector index or embedding store. The normal outputs are `graphify-out/graph.html`, `graphify-out/GRAPH_REPORT.md`, and `graphify-out/graph.json`.

## Role in CivicPulse

Use Graphify to reduce agent time spent blindly grepping through the repository.

```text
Assignment requirements
        ↓
CivicPulse_ImplementationPlan.md   ← authoritative
        ↓
Graphify knowledge graph ← repository understanding / discovery
        ↓
Coding agent
        ↓
Tests + evidence + review
```

Graphify may help an agent answer questions such as:

- Where is a concept implemented?
- What code, tests, configuration, and documentation are connected to a component?
- What depends on a service, repository, provider, cache, or frontend API client?
- What is the path between two concepts or components?
- Which parts of the repository are likely to be affected by a change?
- What surrounding code should be read before editing a file?

Graphify must **not** be used to invent requirements. If Graphify's inferred relationships conflict with explicit source code, tests, `CivicPulse_ImplementationPlan.md`, or the assignment, the explicit source wins.

## Installation for This Project

For a project-scoped Codex setup, install Graphify's skill into the repository:

```bash
uv tool install graphifyy

graphify install --project --platform codex
```

Replace `codex` with the platform your agent uses (see `graphify install --help`).

Then build the repository graph from the project root:

```text
/graphify .
```

On PowerShell, use the CLI form below rather than a leading-slash command if necessary:

```bash
graphify .
```

For subsequent changes, refresh only changed content when appropriate:

```text
/graphify . --update
```

or from the CLI:

```bash
graphify update .
```

After a `git pull`, refresh the graph before trusting a query against newly pulled code:

```bash
graphify update .
```

## Mandatory Agent Preflight

Before implementing a non-trivial CivicPulse task, an agent should perform this sequence:

```text
1. Read CivicPulse_ImplementationPlan.md.
2. Identify the current phase and task acceptance criteria.
3. Inspect the existing source/tests relevant to the task.
4. Refresh Graphify if the repository changed since the last graph build.
5. Query Graphify for the target component and its dependencies.
6. Read the actual files returned by that discovery.
7. Implement one bounded change.
8. Run deterministic tests and required phase checks.
9. Review the diff and evidence.
```

Example discovery commands:

```text
/graphify query "what connects the complaint API to triage and persistence?"

/graphify query "where is rate limiting implemented and what depends on it?"

/graphify path "ComplaintService" "ComplaintRepository"

/graphify explain "RateLimiter"
```

For terminal use, the equivalent graph queries are:

```bash
graphify query "what connects the complaint API to triage and persistence?"
graphify path "ComplaintService" "ComplaintRepository"
graphify explain "RateLimiter"
```

Treat query output as navigation and context. **Always open and inspect the referenced source files before editing them.**

## Agent Prompt Pattern with Graphify

For tasks where repository structure or dependencies are non-trivial, add this preflight to the existing Agent Task Format:

```text
Graphify preflight:
- Refresh the graph if the repository has changed since the previous graph build.
- Query the graph for the task's primary component and its direct dependencies.
- Use path/explain queries where useful to understand relationships.
- Read the actual source, tests, and configuration identified by Graphify.
- Do not treat inferred graph relationships as authoritative requirements.
- Do not edit generated Graphify output to make the graph match the implementation.
```

Then the normal task contract still applies:

```text
Read:
- CivicPulse_ImplementationPlan.md
- relevant existing source/tests
- Graphify results for the target area

Task:
[ONE COHERENT TASK]

Requirements:
- [explicit assignment/plan requirement]

Constraints:
- preserve architecture
- do not modify unrelated behavior
- deterministic tests
- no secrets

Acceptance criteria:
- [criterion]

Tests to run:
- [commands]
```

## Graphify Queries for Each CivicPulse Workstream

### Backend Core

Use Graphify to trace:

```text
route → service → repository → model
route → dependency/configuration
endpoint → test coverage
```

Useful questions:

```text
What connects POST /api/complaints to persistence?
What depends on ComplaintService?
Where are status transitions referenced?
What tests exercise the complaint endpoints?
```

### AI / Redis

Trace:

```text
triage service
    → provider interface
    → provider implementations
    → retry/fallback
    → AI cache

stats endpoint
    → stats service/repository
    → Redis cache

complaint submission
    → distributed rate limiter
```

Useful questions:

```text
What connects triage to the provider factory?
Where is the fallback path called?
What invalidates the AI cache?
What code reads/writes the Redis stats cache?
What depends on the rate limiter?
```

### Frontend

Trace:

```text
page/component → typed API client → endpoint contract
page/component → state/error handling
runtime configuration → API base URL
```

Useful questions:

```text
Which frontend components consume GET /api/stats?
Where is the 409 status rendered?
What depends on the typed API client?
Where is runtime API configuration loaded?
```

### Docker / Compose

Trace configuration dependencies:

```text
Dockerfile → application startup
Compose service → environment variables
Compose service → network
Compose service → healthcheck
Compose volume → persistence
```

Useful questions:

```text
Which services depend on PostgreSQL?
Which services depend on Redis?
Which containers share a network?
Where are database credentials configured?
```

### Kubernetes

Trace:

```text
Deployment → ConfigMap/Secret
Deployment → Service
Deployment → probes
StatefulSet → PVC
HPA → Deployment/resources
Ingress → Service
```

Useful questions:

```text
What connects the backend Deployment to PostgreSQL?
Which manifests provide backend environment variables?
What Service exposes the frontend?
Which resources does the HPA target?
```

### CI/CD

Trace:

```text
workflow → test jobs → image build → scan → publish → deploy → smoke test
workflow job → needs/dependencies
workflow → Kubernetes manifests
```

Useful questions:

```text
What must pass before an image is published?
Which job deploys the SHA-tagged image?
What performs the smoke test?
Where is rollback implemented?
```

## Change Impact Analysis

Before changing a shared component, query Graphify for its neighborhood and paths to major consumers.

Example:

```text
Target: `ComplaintService`

1. explain ComplaintService
2. get/find the surrounding callers and dependencies from the graph
3. inspect the corresponding routes, repositories, providers, and tests
4. identify likely affected acceptance criteria
5. make the smallest compatible change
```

This is especially useful for components that cross workstreams, such as:

```text
ComplaintService
ProviderFactory
RedisCache
RateLimiter
Typed API client
Configuration/settings
Kubernetes ConfigMap/Secret references
CI workflow jobs
```

Do not assume every graph neighbor is a real runtime dependency. Confirm the relationship in source code.

## Keeping the Graph Current

Graphify should be refreshed whenever repository content changes materially:

```text
New code or docs
    ↓
Graphify update
    ↓
New query results
    ↓
Agent implementation/review
```

Recommended moments to refresh:

```bash
# first setup
graphify .

# after pulling or merging changes
graphify update .

# after substantial local implementation work
graphify update .
```

For a repository where the graph should stay synchronized automatically, Graphify also supports a Git hook workflow:

```bash
graphify hook install
```

Use this only as a convenience. The agent must still ensure the graph is current before relying on query results.

## Graphify Output and Evidence

The generated artifacts can be useful during development:

```text
graphify-out/
├── graph.html
├── GRAPH_REPORT.md
└── graph.json
```

They are **development/analysis artifacts**, not proof that an assignment requirement is satisfied.

For CivicPulse, evidence must still come from the real implementation and reproducible checks described elsewhere in this plan. In particular:

```text
Graph relationship found
        ≠
Feature implemented
        ≠
Feature tested
        ≠
Requirement demonstrated
```

Never cite a Graphify edge as a substitute for runtime evidence, test output, Kubernetes output, CI output, or other required evidence.

## EXTRACTED vs INFERRED Relationships

Graphify labels connections as:

```text
EXTRACTED  = explicitly supported by source content
INFERRED  = relationship resolved by Graphify
```

Agents should prefer `EXTRACTED` relationships when making implementation decisions. `INFERRED` relationships are useful for discovery and hypothesis generation, but must be verified against the repository before being used as a basis for code changes.

## Scope and Security Rules

Agents using Graphify must preserve the same repository hygiene rules as the rest of this plan:

- Never place secrets, API keys, or credentials into Graphify queries or generated documentation.
- Do not commit `.env` files or secret material merely because Graphify can discover project files.
- Do not use Graphify output to justify exposing PostgreSQL or Redis.
- Do not add application architecture solely to make the graph look more connected or impressive.
- Do not modify implementation to satisfy an inferred graph relationship without confirming the assignment requirement.
- Do not treat Graphify as a substitute for tests, code review, or the final compliance audit.

## Recommended Graphify Agent Loop

For repository-heavy tasks, use this loop:

```text
READ PLAN
   ↓
REFRESH GRAPH IF NEEDED
   ↓
QUERY TARGET / EXPLAIN CONCEPT
   ↓
TRACE DEPENDENCIES / PATHS
   ↓
READ ACTUAL FILES
   ↓
IMPLEMENT ONE BOUNDED TASK
   ↓
TEST
   ↓
CHECK DIFF
   ↓
DOCUMENT / CAPTURE EVIDENCE
   ↓
REVIEW
   ↓
REFRESH GRAPH
   ↓
MOVE TO NEXT READY TASK
```

This complements the existing phased implementation order and agent work breakdown. Graphify improves **understanding and navigation**; it does not change the order, requirements, or definition of done.
