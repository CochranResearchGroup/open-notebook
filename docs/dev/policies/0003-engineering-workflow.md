# Policy | Engineering Workflow

## Planning And Scope

- Use bounded implementation slices with explicit acceptance criteria when changes span multiple surfaces.
- For larger work, create plans under `docs/dev/plans/` with deterministic filenames such as `0001-YYYY-MM-DD-slug.md`.
- Do not create new top-level workflows, endpoints, provider abstractions, or deployment paths unless the slice needs them and the relevant docs are updated.
- Keep provider-specific behavior at the narrowest layer that can own it cleanly.

## Git And Worktree Hygiene

- Start branch-sensitive work with `git status --short`.
- Treat existing dirty state as user or prior-session work unless proven otherwise.
- Do not revert unrelated changes to make the tree look clean.
- Keep one bounded branch/worktree scope per slice. Prefer `git worktree` over a second clone for parallel work.
- Make commits only when requested or when the task explicitly includes commit/push work.

## Commit Discipline

- Keep commits coherent, truthful, and reviewable.
- Do not mix unrelated feature work, fixes, generated outputs, and refactors in one commit when they can be separated.
- Include rationale in the commit body when runtime behavior, migration, deployment, or operator impact would be unclear from the diff alone.

## Documentation Control

- Update docs in the same slice when behavior, setup, defaults, deployment, provider configuration, or user workflows change.
- Do not rely on chat history as the authoritative explanation for a behavior change.
