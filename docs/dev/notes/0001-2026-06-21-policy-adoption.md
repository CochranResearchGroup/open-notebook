# Note | Policy Adoption

## Summary

Open Notebook adopted repo-local agent policy on 2026-06-21.

The deterministic selector first pass recommended `standalone-library` because the repo did not yet have `AGENTS.md`, `docs/dev/policies/`, `ROADMAP.md`, `RUNBOOK.md`, or plan surfaces. That recommendation was overridden to a custom composition because Open Notebook is a product web application with Python/FastAPI backend code, Next.js frontend code, Docker/live-container deployment paths, and runtime integration work.

## Adopted Local Shape

- `AGENTS.md` is the policy wire-in entrypoint.
- `docs/dev/policies/` stores durable repo-local policy.
- `docs/dev/notes/`, `docs/dev/memories/`, and `docs/dev/plans/` are the canonical continuity directories.
- Graph-backed memory policy names `open-notebook` as the repo-scoped Graphiti group for future compact memory writes.
- Code discovery policy requires CodeGraph first when initialized, codebase-memory/Graphiti for persistent or cross-project context, and `rg`/direct reads for literal strings and exact file checks.

## Deferred

- No `ROADMAP.md` or `RUNBOOK.md` was created in this adoption slice.
- No exact full-profile module dump was installed; the local files compose the relevant shared policy modules into fewer repo-specific files.
