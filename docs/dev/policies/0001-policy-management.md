# Policy | Policy Management

## Adopted Profile

- Selected local shape: custom composition based on `repo-product-engineering` with web/runtime additions.
- Selector first pass chose `standalone-library` because this repo lacked existing roadmap/runbook/policy surfaces; that was overridden because Open Notebook is a full web product with backend, frontend, Docker, live-runtime, and deployment workflows.
- Adopted modules from the shared policy library include policy management, upgrade/adoption feedback, notes and memories, graph-backed memory, CodeGraph, planning, architecture/documentation control, git/worktree hygiene, commit discipline, web interface quality, runtime/product boundary, validation, and closeout.

## Policy

- Keep durable repo-local agent policy under `docs/dev/policies/`.
- Keep `AGENTS.md` thin and use it as the wire-in entrypoint.
- Re-read relevant policy files before non-trivial modifications and when the requested scope changes.
- Preserve repo-local nuance over exact shared-profile wording.
- Record durable policy adoption or upgrade lessons under `docs/dev/notes/` when the experience reveals reusable friction or repo-specific conventions.
- Use `docs/dev/memories/` for stable repo context that future sessions should not rediscover from chat history.
- Do not store secrets, tokens, private auth files, or live user data in policy, notes, memories, or committed examples.

## Current Surface Classification

- Existing `AGENTS.md`: none before adoption.
- Existing `docs/dev/policies/`: none before adoption.
- Existing roadmap/runbook/plans: none before adoption.
- Adoption mode: clean adoption with repo-specific overrides.
