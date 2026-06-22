# Policy | Graph Memory And CodeGraph

## CodeGraph

- Use CodeGraph first for structural source-code work when this repo has an initialized index.
- Prefer CodeGraph for symbol lookup, architecture context, callers/callees, impact analysis, and flow tracing.
- Do not use broad grep/read loops as the first step for structural questions when CodeGraph is available.
- Account for index freshness after edits; use direct source reads and tests for newly changed files.
- If CodeGraph reports that the repo is not initialized, state that fallback and continue with targeted source reads unless the user explicitly wants the index initialized.

## codebase-memory / Graphiti

- Use codebase-memory/Graphiti for persistent or cross-project graph context, prior decisions, durable repo facts, and workspace policy continuity.
- Query repo-scoped memory first when the task is about Open Notebook. Use the group id `open-notebook` when a Graphiti write or repo-scoped lookup is needed.
- Treat graph memory as advisory until verified against repo files, runtime artifacts, commits, tests, or live service readbacks.
- Write to graph memory only for stable, compact, source-anchored facts worth retrieving later. Do not write one-off command output, temporary errors, raw reasoning, secrets, tokens, or credential material.
- Prefer creating a durable repo note or memory file first when the context is narrative or audit-like; mirror only compact retrieval facts to Graphiti when useful.

## Search Fallback

- Use `rg` and direct file reads for literal text, config values, docs, logs, generated artifacts, and exact file checks.
- When graph tools are unavailable, stale, or insufficient, proceed with targeted repo inspection and mention the fallback in handoff if it affects confidence.
