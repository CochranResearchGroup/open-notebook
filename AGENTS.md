# Open Notebook Agent Policy

## Repo Context

- Open Notebook is a product-engineering web application with a Python/FastAPI backend, Next.js frontend, SurrealDB runtime, Docker deployment paths, and local live-container usage.
- Treat this checkout as reusable product code. Keep live data, credentials, mounted Codex homes, caches, uploads, and operator-specific runtime state outside the repo unless a file is an explicit redacted example.
- Current local deployment evidence may live outside the repo under user-scoped runtime paths such as `~/.local/share/open-notebook/`; inspect those paths only when the task is explicitly about the live local deployment.

## Policy Loading Contract

- `AGENTS.md` is the entrypoint; durable policy lives under `docs/dev/policies/`.
- Re-read the relevant policy files at the start of any non-trivial turn and whenever scope changes mid-session.
- Before changing code, read:
  - `docs/dev/policies/0001-policy-management.md`
  - `docs/dev/policies/0002-graph-memory-and-codegraph.md`
  - `docs/dev/policies/0003-engineering-workflow.md`
  - `docs/dev/policies/0004-runtime-ux-and-validation.md`

## Discovery And Editing Defaults

- For structural source-code questions, use CodeGraph first when this repo has an initialized index.
- If CodeGraph is unavailable or not initialized, use codebase-memory/Graphiti where it is relevant for persistent or cross-project context, then fall back to targeted source reads and `rg`.
- Use `rg`/direct reads for literal strings, config values, docs, logs, generated artifacts, and exact file checks.
- Before edits, check the existing dirty state and preserve unrelated user changes.

## Validation Defaults

- Backend changes: run focused pytest and ruff for touched Python surfaces; widen to `uv run pytest tests/ -q` and `uv run ruff check .` for cross-cutting changes.
- Frontend changes: run the relevant npm lint/test/build command from `frontend/` when the touched surface warrants it.
- Live deployment changes: verify the container, local loopback endpoints, and public route when those surfaces are in scope.
