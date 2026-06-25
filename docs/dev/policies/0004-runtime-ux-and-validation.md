# Policy | Runtime, UX, And Validation

## Runtime/Product Boundary

- Keep reusable code, templates, docs, redacted fixtures, and deterministic examples in the repo.
- Keep live data, uploads, credentials, auth files, mounted Codex homes, caches, logs, and private operator state in user-scoped runtime homes outside the repo.
- When modifying Docker or live deployment behavior, verify both the product code path and the actual running container if the live instance is in scope.
- Never print secrets or credential contents in logs, command output summaries, docs, notes, or final handoff.

## Web Interface Quality

- Treat settings, provider management, model selection, empty states, loading states, errors, and permission failures as part of the UX contract.
- Use existing frontend patterns and component conventions before introducing new UI structure.
- Verify meaningful UX changes in browser or with frontend tests/builds when practical.
- Preserve accessible labels, focus behavior, responsive layout, and clear validation feedback.

## Validation

- Run validation that matches the touched surface before claiming work complete.
- For backend and cross-cutting Python changes, prefer focused pytest plus ruff, then widen when behavior is shared or user-visible.
- For frontend changes, run the relevant frontend lint/test/build path from `frontend/`.
- For live deployment changes, verify container state, local health endpoints, auth boundaries, and public route behavior as appropriate.
- For changes expected to appear on `https://open-notebook.ecochran.dyndns.org/`, follow `docs/dev/runbooks/cooper-live-deployment.md` or explicitly state that the live deploy was skipped. A commit or push alone does not update the live site.
- State exactly what validation ran, what passed, and what remains unverified.

## Closeout

- End with the best concrete recommendation or next slice when one is available.
- Keep closeout concise and evidence-backed.
- Distinguish implemented, configured, deployed, live-tested, and merely planned work.
