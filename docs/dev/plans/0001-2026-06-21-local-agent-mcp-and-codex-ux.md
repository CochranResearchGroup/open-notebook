# Plan 0001 | Local Agent MCP And Codex UX

State: COMPLETE
Date: 2026-06-21

## Goal

Make Open Notebook a first-class participant in the local agent environment:

- Open Notebook can call local MCP servers as tools during LLM workflows.
- Open Notebook exposes first-class UX for configuring Codex App Server as the default language model.
- Open Notebook exposes a supported MCP surface so Codex, OpenClaw, and other local agent sessions can read and mutate notebooks, sources, notes, models, settings, and workflows.

## Current State

- Open Notebook already has a normal HTTP API, an internal `APIClient`, password bearer auth, model/defaults endpoints, credential/provider UX, and docs that point users to an external `open-notebook-mcp` package.
- A `codex_app_server` language provider exists in this checkout and works through `codex app-server --listen stdio://`, but the frontend provider-card UX does not yet expose it as a first-class configurable provider.
- The Codex App Server wrapper currently treats Codex as a non-interactive LLM and replies with errors to server-originated app-server requests. It does not yet broker MCP tools into Codex turns.
- No repo-owned MCP server entrypoint is currently present in `pyproject.toml`; the docs describe an external PyPI server.
- CodeGraph is not initialized in this checkout at plan creation time, so source discovery for this plan used targeted reads and existing docs.

## Progress

### 2026-06-21 | Track A implementation

- Added backend Codex App Server runtime status, sync, and set-language-defaults endpoints.
- Added first-class Codex App Server frontend provider card with runtime status, sync/register action, model test action, and language-default assignment action.
- Updated docs and environment reference for UX-driven Codex setup.
- Validation passed:
  - `uv run ruff check .`
  - `uv run pytest tests/ -q` (`207 passed`)
  - `npm run lint` (`0 errors`, pre-existing warnings remain outside this slice)
  - `npm run build`

### 2026-06-21 | Track C minimal implementation

- Added a repo-owned `open-notebook-mcp` console script backed by the existing `api.client.APIClient`.
- Initial MCP tool surface is conservative:
  - read-only: list/get notebooks, list notes, list sources, search, list models, get default models
  - write-safe: create notebooks, create notes
  - high-risk delete/rebuild/long-running mutation tools remain out of scope for this first slice
- Updated MCP docs with first-party stdio launch snippets for local agents.
- Validation passed:
  - `uv run ruff check .`
  - `uv run pytest tests/ -q` (`209 passed`)

### 2026-06-21 | Track B minimal implementation

- Added a persisted MCP server configuration model and migration for local MCP client configuration.
- Added authenticated API endpoints under `/api/mcp/servers`:
  - list/create/update/delete configured servers
  - test a server and inspect advertised MCP tools
- Added a stdio MCP client inspection service using the official MCP client session. Network transports are represented in the config schema but are not yet runtime-tested.
- Added an Advanced-page MCP server panel for adding stdio servers, toggling enabled state, deleting configs, testing connections, and inspecting tool permission badges.
- Responses redact environment variable values and expose only environment variable names. Private tokens should remain in environment references or credential storage.
- Bridging selected MCP tools into chat/model execution remains pending for the next Track B/D slice.
- Validation passed:
  - `uv run pytest tests/test_mcp_client_config.py tests/test_mcp_server.py -q`
  - `uv run ruff check api/routers/mcp_servers.py api/models.py open_notebook/domain/mcp_server_config.py open_notebook/mcp_client.py tests/test_mcp_client_config.py`
  - `npm run lint` (`0 errors`, pre-existing warnings remain outside this slice)
  - `npm run build`

### 2026-06-21 | Track B read-only tool-call implementation

- Added governed stdio MCP `call_tool` support with:
  - server enabled checks
  - per-tool disabled/allowlist checks
  - read vs mutate classification checks
  - bounded text-result normalization
  - safe failure responses through `/api/mcp/tool-call`
- Added explicit notebook-chat MCP command handling:
  - `/mcp <server-id> <tool-name> <json-args>`
  - only calls tools classified as `read`
  - injects the tool result into that chat turn before the configured chat model answers
  - leaves normal chat messages unchanged
- Extended Advanced MCP UX so inspected tools can be enabled/disabled and classified as `read` or `mutate`, and enabled read-only tools show a chat command snippet.
- Added frontend API/hook types for direct MCP tool calls.
- Added MCP tool-call audit records and `/api/mcp/tool-audit` readback:
  - stores server/tool names, caller, status, permission class, argument-key summary, and result-size summary
  - avoids storing raw argument values or raw result text
- Remaining Track B/D work:
  - mediated model-native tool calling rather than command-triggered context injection
  - network transport runtime support
  - Codex-native MCP profile association

### 2026-06-21 | Track D Codex MCP profile association

- Added a persisted Codex MCP profile preference with modes:
  - `none`
  - `read_only`
  - `selected`
  - `custom`
- Added Codex provider endpoints:
  - `GET /api/models/codex-app-server/mcp-profile`
  - `PUT /api/models/codex-app-server/mcp-profile`
- Added safe Codex MCP TOML preview generation for enabled stdio MCP servers:
  - environment values are rendered as placeholders like `${TOKEN}` rather than stored values
  - `read_only` mode excludes servers that Open Notebook has classified with mutating tools
  - the response includes warnings that Codex-native MCP bypasses Open Notebook per-tool enforcement
- Added Codex App Server provider-card UX to select the profile mode, select servers, save preferences, and preview generated config.
- Then-remaining Track D work:
  - actually pass a generated/selected Codex profile into a Codex app-server process
  - prove an allowlisted read-only MCP tool is used by Codex itself, not just Open Notebook-mediated chat

### 2026-06-21 | Track D Codex dynamic tool-call handling

- Verified the local Codex app-server generated protocol for this installed Codex CLI:
  - server-originated dynamic tool calls use `item/tool/call`
  - `DynamicToolCallParams` include `namespace`, `tool`, and JSON `arguments`
  - `DynamicToolCallResponse` returns `contentItems` and `success`
- Added Open Notebook-mediated dynamic tool specs for the Codex App Server wrapper:
  - selected read-only MCP tools are advertised in `thread/start` config under the `open_notebook_mcp` namespace
  - tool names are prefixed with their configured MCP server name to avoid collisions
- Added Codex server request handling:
  - `item/tool/call` is routed through Open Notebook MCP permission checks with `allow_mutation=False`
  - results are returned in Codex dynamic-tool response shape
  - failures return `success: false` tool output instead of aborting the app-server read loop
  - calls are audited with caller `codex_app_server`
- Kept explicit unsupported-request behavior for other server-originated request methods, including auth refresh guidance.
- Then-remaining Track D work:
  - live Codex runtime proof that a model actually chooses and invokes an advertised read-only MCP dynamic tool
  - decide whether the generated Codex-native TOML preview should be materialized into an operator-selected runtime profile

### 2026-06-21 | Track D live dynamic-tool smoke attempt

- Added `tests/smoke/codex_dynamic_tool_smoke.py` to exercise the installed `codex app-server` with a runtime-only verification token exposed only through a mocked Open Notebook dynamic tool callback.
- The installed local Codex CLI reports `codex-cli 0.141.0` and starts `codex app-server --listen stdio://`.
- Initial live smoke result:
  - Codex emitted `mcpServer/elicitation/request`; the wrapper now handles that request by returning a documented `decline` response instead of an unsupported-request error.
  - Codex did not emit `item/tool/call` for the advertised `open_notebook_mcp` dynamic tool (`tool_call_count=0`).
  - One run returned only the public prefix `open-notebook-dynamic-tool-smoke`; after elicitation handling, a run timed out before turn completion.
  - A short structured rerun logged `resources/list failed: unknown MCP server 'open_notebook_mcp'`, which suggests the current `experimental_dynamic_tools` config shape is not enough to register `open_notebook_mcp` as a usable Codex tool namespace.
- Current boundary:
  - deterministic tests prove Open Notebook can advertise dynamic tool specs and can answer `item/tool/call` if Codex emits it.
  - live Codex runtime proof of dynamic-tool invocation is still open.
  - the next slice should identify the exact Codex app-server dynamic-tool registration contract, or pivot to materializing the generated Codex-native MCP TOML profile as the supported runtime path.

### 2026-06-21 | Track D Codex-native MCP launch path

- Pivoted the default Codex App Server MCP launch path from `experimental_dynamic_tools` to Codex-native MCP configuration.
- Added per-process Codex MCP config override generation:
  - reads the saved Codex MCP profile preference
  - selects enabled stdio servers from `read_only` or `selected` modes
  - passes env-free selected servers to `codex app-server` with process-local `-c mcp_servers...` overrides
  - originally skipped servers with stored environment values so secrets were not exposed through process arguments
- Kept the dynamic-tool handler and smoke script, but made dynamic-tool advertising opt-in with `OPEN_NOTEBOOK_CODEX_APP_SERVER_DYNAMIC_TOOLS=true`.
- Added managed-profile materialization support for future file-based Codex profile work:
  - writes outside the repo under Codex home
  - uses `0600`
  - keeps API preview output redacted
- Runtime evidence:
  - `codex -c 'mcp_servers.open_notebook_mcp.command="python3"' -c 'mcp_servers.open_notebook_mcp.args=["-c","print(123)"]' mcp list` lists the configured MCP server.
  - `codex --profile open-notebook-mcp mcp list` did not list a sibling `$CODEX_HOME/open-notebook-mcp.config.toml` profile in this CLI build, so the active launch path uses `-c` overrides instead of relying on profile-file layering.
- Then-remaining Track D work:
  - live end-to-end Codex model proof that a selected env-free read-only MCP server is used during an Open Notebook Codex chat turn
  - safe native Codex support for env-bearing MCP servers without leaking secrets through process arguments
  - broader browser/UX QA for the profile selector and warning copy

### 2026-06-21 | Track D live Codex-native MCP proof

- Added `tests/smoke/codex_native_mcp_server.py`, an env-free FastMCP smoke server with one read-only tool.
- Added `tests/smoke/codex_native_mcp_smoke.py` with two live modes:
  - `--mode direct`: starts the real `codex app-server`, lists configured MCP status, and calls `mcpServer/tool/call` directly.
  - `--mode model`: starts the real `codex app-server`, prompts the model to use the configured MCP tool, and verifies the smoke server call log plus final marker response.
- Direct proof passed:
  - `call_count=1`
  - `status_response_contains_server=true`
  - `call_response_contains_marker=true`
- Model proof initially failed with `user rejected MCP tool call`.
  - The recorded server request was `mcpServer/elicitation/request`.
  - Its `_meta.codex_approval_kind` was `mcp_tool_call`.
- Updated the Codex App Server wrapper to:
  - accept only MCP tool-call elicitations with `action=accept` and empty form content
  - continue declining other MCP elicitations
  - respond to turn-scoped permission approval requests
- Live model proof then passed:
  - `server_request_methods=["mcpServer/elicitation/request"]`
  - `call_count=1`
  - `tool_called=true`
  - `response_contains_marker=true`
- Current boundary:
  - Track D env-free read-only Codex-native MCP use is now live-proven through the installed Codex CLI/app-server.
  - browser/UX QA for the MCP profile selector remains pending.

### 2026-06-21 | Track D env-bearing Codex-native MCP proof

- Added a Codex MCP launch configuration helper that chooses the safe runtime shape:
  - env-free selected stdio MCP servers still use process-local `-c mcp_servers...` overrides
  - env-bearing selected stdio MCP servers use a private temporary Codex home instead of argv
  - the temporary Codex home symlinks local `auth.json*` files from the configured Codex home, writes a managed `config.toml` with mode `0600`, and is removed after the app-server process exits
- Extended `tests/smoke/codex_native_mcp_server.py` so the smoke marker can be read from an MCP server environment variable.
- Extended `tests/smoke/codex_native_mcp_smoke.py` with `--env-bearing`.
- Live direct env-bearing proof passed:
  - `mode=direct`
  - `env_bearing=true`
  - `call_count=1`
  - `call_response_contains_marker=true`
  - `status_response_contains_server=true`
- Live model env-bearing proof passed:
  - `mode=model`
  - `env_bearing=true`
  - `call_count=1`
  - `tool_called=true`
  - `response_contains_marker=true`
- Current boundary:
  - Track D Codex-native MCP use is now live-proven for both env-free and env-bearing selected stdio MCP servers.
  - env-bearing native MCP config no longer leaks MCP env values through process arguments.
  - browser/UX QA for the MCP profile selector remains pending.

### 2026-06-21 | Track D Codex MCP profile browser QA

- Browser-tested the Codex App Server provider card and Codex MCP profile selector against the current checkout using:
  - local API on `127.0.0.1:5055`
  - local frontend on `localhost:3000`
  - isolated temporary SurrealDB database
  - disposable stdio MCP server config with one environment key
- Verified profile modes:
  - `none`: no generated Codex MCP config
  - `selected`: selectable server row, successful save, direct-Codex warning, generated TOML preview
  - `read_only`: successful save and read-only server inclusion
  - `custom`: external-profile warning and no generated Open Notebook config
- Verified the generated TOML preview renders environment values as placeholders such as `${QA_PLAN0001_MARKER}` and does not expose the stored value.
- Fixed a UX copy issue found during QA: MCP profile save now shows `Codex MCP profile saved successfully` instead of the generic model-save toast.
- Retained QA evidence in `reports/plan-0001-ux-qa/report.md`.
- Validation passed:
  - `npm run lint` (`0 errors`, pre-existing warnings remain outside this slice)
  - `npm run build`
- Current boundary:
  - Track D Codex-native MCP behavior and browser UX are now live-proven for this slice.
  - Final Plan 0001 closeout was completed in the acceptance audit below.

### 2026-06-21 | Final acceptance audit and closeout

- Fixed a first-party MCP server packaging bug found during closeout:
  - the `open-notebook-mcp` console script could fail outside repo-root execution because `api.client` is not part of the packaged `open_notebook` module
  - `open_notebook.mcp_server` now includes a small packaged HTTP client fallback for the conservative MCP tool surface
- Added and passed `tests/smoke/open_notebook_mcp_smoke.py`:
  - starts the first-party `open-notebook-mcp` server over stdio
  - lists advertised tools
  - calls `list_notebooks`
  - calls write-safe `create_note` through the Open Notebook API
- Added and passed `tests/smoke/codex_open_notebook_mcp_smoke.py`:
  - starts the installed `codex app-server`
  - configures the actual first-party `open-notebook-mcp` server through a private temporary Codex home
  - verifies Codex MCP status contains `open_notebook`
  - calls `list_notebooks`
  - calls write-safe `create_note` and verifies the smoke marker in the response
- Final validation passed:
  - `uv run tests/smoke/open_notebook_mcp_smoke.py --open-notebook-url http://127.0.0.1:5055 --open-notebook-password ...`
  - `uv run tests/smoke/codex_open_notebook_mcp_smoke.py --open-notebook-url http://127.0.0.1:5055 --open-notebook-password ...`
  - `uv run pytest tests/test_mcp_server.py tests/test_mcp_client_config.py tests/test_codex_app_server.py -q` (`33 passed`)
  - `uv run ruff check open_notebook/mcp_server.py tests/smoke/open_notebook_mcp_smoke.py`
  - `uv run ruff check tests/smoke/codex_open_notebook_mcp_smoke.py`
  - `uv run ruff check .`
  - `uv run pytest tests/ -q` (`235 passed`)
  - `npm run lint` (`0 errors`, pre-existing warnings remain outside this slice)
  - `npm run build`
- Acceptance audit result:
  - Track A complete: Codex App Server provider UX, runtime status, sync/test/default actions, tests, docs, browser QA.
  - Track B complete for this bounded slice: persisted stdio MCP config, Advanced UX, tool inspection, read-only chat command, governed tool-call API, redacted audit records, tests.
  - Track C complete for this bounded slice: repo-owned MCP server, conservative read/write-safe tool surface, local-agent docs, first-party MCP stdio smoke, Codex-native direct smoke.
  - Track D complete: Codex profile selector, Codex-native MCP launch path, env-free and env-bearing live Codex MCP proofs, browser QA.
  - Track E complete for this bounded slice: conservative defaults, redaction, timeout/permission checks, audit records, security docs, no committed private runtime state.

## Non-Goals

- Do not commit private MCP server configs, Codex auth files, API passwords, or local runtime paths.
- Do not make public unauthenticated mutation tools.
- Do not expose arbitrary shell/file access through Open Notebook MCP tools.
- Do not replace the existing HTTP API. MCP should wrap and govern it, not fork business logic.
- Do not require cloud dependencies for local agent interoperability.

## Design Principles

- HTTP API remains the product authority for Open Notebook mutations.
- MCP tools should call existing service/API layers, not duplicate database logic.
- Local MCP server access from Open Notebook should be explicitly configured, allowlisted, and visible in UX.
- Mutating MCP tools must be named, scoped, and auditable.
- Defaults should be recoverable: if Codex or an MCP server is unavailable, the UX should show degraded state and preserve existing model/default settings.
- Runtime state belongs outside the repo; committed files should be examples, schemas, docs, and tests.

## Track A | First-Class Codex App Server UX

### Scope

Expose the existing `codex_app_server` backend provider fully in the settings UI.

### Work

1. Add `codex_app_server` to frontend provider constants:
   - display name: `Codex App Server`
   - modality: `language`
   - documentation link to repo docs
   - provider card shown with environment/runtime status
2. Add a provider-specific Codex configuration panel that does not ask for an API key:
   - enabled/disabled status
   - Codex binary path or detected binary
   - Codex profile
   - Codex home status without revealing secrets
   - model name
   - effort
   - sandbox mode
   - working directory
   - timeout
3. Add backend read-only status endpoint for Codex runtime health:
   - CLI found
   - `codex app-server --help` works
   - configured model name
   - configured sandbox/effort
   - Codex home path present/redacted
   - last test result, if available
4. Add safe backend write/update endpoint for Codex settings if repo design accepts DB-backed app settings; otherwise keep settings env-only and make the UX explicit.
5. Add one-click actions:
   - sync/register Codex model
   - test Codex model
   - set Codex as language defaults
   - restore previous language defaults
6. Update docs and `.env.example` for UX-driven setup and Docker deployment.

### Acceptance Criteria

- A user can see Codex App Server in the Models/settings page without manual DB edits.
- A user can register/test the Codex model from the UX.
- A user can make Codex the default chat/transformation/tools/large-context model from the UX.
- The UI never displays token/auth contents.
- Backend tests cover status, discovery, sync, default assignment, and failure states.
- Frontend tests or browser QA cover the provider card and default assignment flow.

## Track B | Open Notebook As MCP Client

### Scope

Allow Open Notebook LLM workflows to call configured local MCP servers as tools.

### Work

1. Define an MCP server config model:
   - name
   - transport type: `stdio`, `http`, `sse`, or `websocket` as supported by the chosen MCP client library
   - command/args/env for stdio servers
   - URL and auth metadata for network transports
   - enabled flag
   - allowed tool names or denylisted tool names
   - read-only vs mutation-capable classification
   - timeout and concurrency limits
2. Store MCP config safely:
   - non-secret config in SurrealDB or settings table
   - secrets in existing encrypted credential mechanism or environment references
   - no committed private runtime config
3. Build an MCP client service:
   - list servers
   - health check server
   - list tools/resources/prompts
   - call tool with timeout
   - normalize errors for UI and LLM use
   - redact args/results in logs where needed
4. Add UX under Settings or Advanced:
   - add/edit/remove MCP server
   - test connection
   - inspect advertised tools
   - mark individual tools as enabled/disabled
   - classify tools as read-only or mutating
5. Bridge MCP tools into LLM workflows:
   - start with explicit chat/session tool use rather than every background job
   - expose selected tools to the active model only when the model path supports tool calling
   - for Codex App Server, decide whether MCP tools are passed through Codex config/app-server or mediated by Open Notebook directly
6. Add guardrails:
   - no arbitrary auto-discovery from user home by default
   - no mutation-capable tools enabled without explicit user action
   - per-tool audit records for mutating calls
   - bounded payload sizes

### Acceptance Criteria

- User can configure a local MCP server in the UX and see its tools.
- User can enable a read-only MCP tool and call it from an Open Notebook chat workflow.
- Mutating MCP tools require explicit configuration and leave an audit trail.
- Failed MCP servers degrade gracefully and do not break normal notebook/chat use.
- Tests cover config validation, tool listing, tool call success/failure, disabled tools, and redaction.

## Track C | Open Notebook As MCP Server

### Scope

Make Open Notebook itself available to local agents through a supported MCP server so Codex, OpenClaw, Claude Desktop, VS Code, and other local sessions can read and mutate Open Notebook through governed tools.

### Work

1. Decide ownership model:
   - Option 1: keep relying on external `open-notebook-mcp`, but add compatibility tests and first-party docs/config export.
   - Option 2: vendor or add a repo-owned MCP server package/entrypoint backed by `api/client.py`.
   - Option 3: hybrid: keep external package for public registry while maintaining a repo-local reference server for local development and tests.
2. Define tool surface tiers:
   - read-only: list/get notebooks, sources, notes, models, settings, search
   - write-safe: create notes, add text/link sources, create notebooks
   - high-risk: delete/update records, trigger transformations, rebuild embeddings, run long LLM jobs
3. Implement or verify MCP tools against the HTTP API:
   - notebook CRUD
   - source CRUD and source ingestion
   - note CRUD
   - search and ask
   - model listing/defaults
   - settings read/update where safe
   - transformations execution where explicitly enabled
4. Add auth and transport guidance:
   - local stdio command for Codex/OpenClaw
   - local HTTP/SSE option if needed
   - bearer password support using `OPEN_NOTEBOOK_PASSWORD`
   - optional tool-scope token if needed later
5. Add config export UX:
   - generate Codex MCP config snippet
   - generate OpenClaw/local agent config snippet
   - generate Claude Desktop / VS Code snippets
   - never include secrets by default; show placeholders or copy-with-secret only after explicit confirmation if implemented
6. Add mutation guardrails:
   - dry-run mode where meaningful
   - confirmation-required tool variants for high-risk operations
   - stable object identifiers in responses
   - audit logging for mutating tool calls

### Acceptance Criteria

- A local Codex session can connect to Open Notebook MCP and list notebooks.
- A local agent can create a note through MCP using the Open Notebook API.
- Dangerous tools are disabled by default or clearly gated.
- MCP server tests cover at least one read-only and one write-safe flow.
- Docs include working snippets for Codex, OpenClaw, Claude Desktop, and VS Code.

## Track D | Codex App Server With Local MCP Tools

### Scope

Close the loop so Codex running as Open Notebook's default LLM can use local MCP tools deliberately.

### Work

1. Decide tool execution architecture:
   - Codex-native MCP: generate a Codex config/profile that points at selected local MCP servers.
   - Open Notebook mediated tools: Open Notebook handles MCP calls and exposes results to the model workflow.
   - Hybrid: Codex-native for trusted local read tools, Open Notebook mediated for mutating/audited tools.
2. Add UX to associate MCP tool profiles with the Codex provider:
   - no tools
   - read-only local tools
   - selected tools
   - custom profile
3. Update the Codex app-server wrapper:
   - stop returning blanket errors for all server-originated requests once supported request types are identified
   - handle or intentionally reject only unsupported app-server requests with clear diagnostics
   - surface tool-call failures in model test output
4. Keep sandbox posture explicit:
   - default `read-only`
   - approval `never` for unattended Open Notebook flows
   - no host filesystem mutation unless the user enables a stronger profile outside normal defaults

### Acceptance Criteria

- Codex default model can complete a normal Open Notebook chat with no MCP tools enabled.
- Codex default model can use an allowlisted read-only MCP tool when enabled.
- Mutating tool access is visibly configured and auditable.
- Tests cover unsupported server-request behavior and at least one supported tool-capable path.

## Track E | Security, Audit, And Runtime Boundaries

### Scope

Keep the local-agent bridge safe enough for a password-protected self-hosted app.

### Work

1. Threat model:
   - local compromised MCP server
   - prompt injection from notebook/source content
   - malicious tool output
   - accidental destructive mutation by local agent
   - credential leakage through config export or logs
2. Add audit records for mutating MCP calls:
   - caller/server name
   - tool name
   - target object ids
   - timestamp
   - success/failure
   - redacted argument summary
3. Add rate limits/timeouts for MCP tool calls.
4. Add per-server and per-tool enablement.
5. Add documentation for safe local deployment and private runtime homes.

### Acceptance Criteria

- Security docs explain the difference between read-only, write-safe, and high-risk tools.
- Logs and API responses do not expose secrets.
- Mutating tool calls are auditable.
- Default config is conservative.

## Suggested Implementation Order

1. Track A: first-class Codex UX, because backend support already exists and this closes the immediate configuration gap.
2. Track C minimal: repo-owned or verified MCP server read/write-safe slice, because external agents need a stable Open Notebook MCP surface.
3. Track B minimal: configure and list local MCP servers in the UX, then support one read-only tool call.
4. Track D: wire selected MCP tools into Codex App Server flows once the client/server surfaces and guardrails exist.
5. Track E hardening: audit logs, permission tiers, docs, and broader tests.

## First Slice Proposal

Implement Track A in one bounded slice:

- Add frontend provider constants for `codex_app_server`.
- Add backend `/api/codex-app-server/status` or equivalent.
- Add provider-card UX for status/test/sync/default assignment.
- Add docs updates.
- Validate with focused backend tests, frontend lint/test for settings page, and live smoke if deployed.

## Open Decisions

- Should Open Notebook own an MCP server package in this repo, or keep the external `open-notebook-mcp` package as the canonical MCP server?
- Should MCP server configs be stored in SurrealDB, local runtime files, or both?
- Should mutating MCP tools require a separate token/scope beyond `OPEN_NOTEBOOK_PASSWORD`?
- Should Codex use MCP tools natively through Codex config, or should Open Notebook mediate tool calls for auditability?
- Which OpenClaw transport/config format should be generated first?
