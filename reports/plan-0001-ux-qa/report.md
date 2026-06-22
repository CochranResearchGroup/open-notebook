# Dogfood Report: Open Notebook Plan 0001 Codex MCP UX

| Field | Value |
|-------|-------|
| **Date** | 2026-06-21 |
| **App URL** | http://localhost:3000/settings/api-keys |
| **Session** | open-notebook-plan0001 |
| **Scope** | Codex App Server provider card and Codex MCP profile selector |

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| **Total** | **0** |

## Evidence

- Initial Codex provider card state: `screenshots/codex-panel-initial.png`
- Selected-server state with redacted env placeholder: `screenshots/codex-panel-selected-server.png`

## Coverage

- Verified the current checkout, not the stale live container image, by running a local dev API on `127.0.0.1:5055` and frontend on `localhost:3000`.
- Seeded one disposable enabled stdio MCP server with an environment key.
- Verified Codex App Server runtime fields render without auth/token contents.
- Verified profile modes:
  - `No tools`: no generated Codex MCP config.
  - `Selected servers`: selectable server row appears, save succeeds, warning appears, generated TOML uses `${QA_PLAN0001_MARKER}` placeholder.
  - `Read-only local`: save succeeds and includes the read-only QA server with the same placeholder.
  - `Custom profile`: save succeeds, external-profile warning appears, no generated config.
- Verified browser console/page errors after the selected-server save; no page errors were reported.
- Fixed one copy issue found during QA: MCP profile save toast now says `Codex MCP profile saved successfully`.
