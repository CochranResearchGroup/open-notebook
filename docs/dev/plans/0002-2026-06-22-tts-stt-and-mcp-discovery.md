# Plan 0002 | TTS/STT Setup And MCP Discovery

## Status

- State: complete
- Started: 2026-06-22
- Owner: local operator / Codex
- Branch: `codex/plan-0001-local-agent-mcp`

## Goal

Make Open Notebook usable as a local agent/audio control plane by:

- wiring practical speech-to-text (STT) and text-to-speech (TTS) provider setup into the existing Models/API Keys UX,
- supporting the locally available AssemblyAI and OpenAI Whisper-family transcription paths,
- showing local MCP servers in the frontend,
- allowing agent-driven MCP configuration through both HTTP API and the first-party Open Notebook MCP server,
- keeping live deployment and validation evidence explicit.

## Current Evidence

- Open Notebook already has `Model` types for `speech_to_text` and `text_to_speech`.
- Default model assignments already include `default_speech_to_text_model` and `default_text_to_speech_model`.
- Credential provider metadata currently includes OpenAI, Google, Groq, Mistral, xAI, ElevenLabs, Deepgram, Azure, and OpenAI-compatible audio-related modalities.
- AssemblyAI is not currently a first-class provider in credential/provider metadata.
- Deepgram is currently marked as `text_to_speech` only in Open Notebook provider metadata, even though OpenClaw treats Deepgram as an audio transcription provider.
- Open Notebook already has manual MCP server CRUD at `/api/mcp/servers`.
- Open Notebook already has a first-party MCP server (`open_notebook/mcp_server.py`) with notebook, note, source, search, model, and default-model tools.
- Open Notebook does not yet expose MCP server configuration tools through its first-party MCP server.
- Open Notebook does not yet discover/import local MCP servers from local agent runtimes such as Codex/OpenClaw config.
- CodeGraph is not initialized in this checkout, so current planning and execution use targeted source reads.

## External Alignment

OpenClaw's current local distro recommends:

- STT auto-detection order: active reply model, local CLIs, Gemini CLI, then provider auth.
- Local STT: `sherpa-onnx-offline`, `faster-whisper` skill wrapper, `whisper-cli` / `whisper-cpp`, and Python `whisper`.
- Provider STT fallback order: OpenAI, Groq, xAI, Deepgram, OpenRouter, Google, SenseAudio, ElevenLabs, Mistral.
- OpenAI default STT: `gpt-4o-mini-transcribe`; higher accuracy: `gpt-4o-transcribe`.
- Talk/TTS priority: ElevenLabs, MLX/local TTS, system TTS, with OpenAI realtime for realtime voice.

Current provider documentation indicates:

- OpenAI supports `gpt-4o-mini-transcribe`, `gpt-4o-transcribe`, `gpt-4o-transcribe-diarize`, and `whisper-1`.
- AssemblyAI supports pre-recorded and streaming STT, including Universal / Universal-3 style models.
- Deepgram supports STT and TTS stacks.
- ElevenLabs supports both TTS and Scribe STT.

## Design Principles

- Reuse the existing credential, model registration, and default assignment primitives.
- Prefer provider metadata and model registration over hardcoded runtime shortcuts.
- Keep secrets outside the repo and never echo runtime env contents.
- Treat local MCP servers as operator-controlled runtime configuration, not product defaults.
- Make agent-driven MCP configuration explicit and auditable.
- Keep mutating MCP tool access disabled or classified unless intentionally enabled.
- Do not claim live availability until the Cooper live deployment runbook has been followed.

## Target UX

### Settings / API Keys

The API Keys / Models page should show:

- provider cards for AssemblyAI, OpenAI, ElevenLabs, Deepgram, local/Ollama where applicable,
- TTS/STT badges that match actual supported modalities,
- discovered audio models that can be registered as `speech_to_text` or `text_to_speech`,
- Default Model Assignments with non-empty STT/TTS choices once models are registered,
- a concise Audio Setup panel that identifies missing STT/TTS defaults.

### Local MCP Servers

The UX should show:

- configured MCP servers,
- discovered local MCP server candidates from supported local agent config sources,
- source labels such as Codex, OpenClaw, environment, or manual,
- whether each candidate is already imported,
- an import/enable action,
- test result and tool count,
- whether each server is included in the Codex App Server MCP profile.

## Target API

### Audio Provider Setup

Use the existing credential and model APIs wherever possible:

- `GET /api/credentials/status`
- `GET /api/models/providers`
- `POST /api/credentials`
- `POST /api/credentials/{id}/discover`
- `POST /api/credentials/{id}/register-models`
- `PUT /api/models/defaults`

Add provider metadata for:

- `assemblyai`
- Deepgram STT modality support
- OpenAI STT/TTS curated model discovery where provider discovery omits audio models

### MCP Discovery And Import

Add:

- `GET /api/mcp/discover-local`
  - returns safe local MCP server candidates, with no secret values,
  - sources candidates from Codex config first,
  - leaves OpenClaw and other runtime discovery as additive providers.
- `POST /api/mcp/import-local`
  - imports one discovered candidate into `MCPServerConfig`,
  - deduplicates by source and stable signature,
  - defaults imported servers to enabled with conservative read-only behavior where possible.

### Agent-Driven MCP Configuration

Extend the first-party Open Notebook MCP server with tools:

- `list_mcp_servers`
- `discover_local_mcp_servers`
- `create_mcp_server`
- `update_mcp_server`
- `test_mcp_server`
- `delete_mcp_server`
- `get_codex_mcp_profile`
- `update_codex_mcp_profile`

Mutation tools should be clearly named, documented, and rely on the same authenticated HTTP API as the frontend.

## Implementation Slices

### Slice 1: Audio Provider Metadata

Work:

- Add `assemblyai` to backend provider env config.
- Add AssemblyAI modalities as `speech_to_text`.
- Add AssemblyAI to frontend provider lists and display names.
- Correct Deepgram modalities to include `speech_to_text` and `text_to_speech` where supported by the product integration.
- Add curated audio model discovery entries for providers whose list APIs do not expose audio models reliably.

Acceptance:

- `/api/credentials/env-status` reports AssemblyAI status.
- `/api/models/providers` includes AssemblyAI when configured.
- Settings page can create AssemblyAI credentials.
- Discovery can return at least one AssemblyAI STT model candidate.

### Slice 2: Audio Defaults UX

Work:

- Ensure TTS/STT registered models show in Default Model Assignments.
- Add small guidance/empty state when STT/TTS defaults are missing.
- Add recommended STT/TTS model labels where known.

Acceptance:

- A registered STT model can be selected as `default_speech_to_text_model`.
- A registered TTS model can be selected as `default_text_to_speech_model`.
- Missing STT/TTS defaults are visible without reading backend JSON.

### Slice 3: Local MCP Discovery API

Work:

- Implement safe discovery of local MCP server candidates.
- Start with Codex config TOML discovery from mounted or host-visible Codex home paths.
- Return only non-secret config and env key names.
- Mark already-imported candidates.

Acceptance:

- `GET /api/mcp/discover-local` returns a stable list of candidates or an empty list with searched sources.
- No secret values are returned.
- Existing configured MCP servers are detected as already imported.

### Slice 4: MCP Import API And Frontend

Work:

- Add `POST /api/mcp/import-local`.
- Add frontend hooks/types/API methods.
- Add a "Discovered local MCP servers" panel to the existing Advanced MCP page or Codex App Server settings card.
- Include import, test, enable, and Codex-profile inclusion affordances.

Acceptance:

- A discovered local MCP server can be imported from the frontend.
- Imported servers appear in the configured MCP server list.
- Imported servers can be tested and included in Codex MCP profile selection.

### Slice 5: First-Party Open Notebook MCP Tools

Work:

- Extend `open_notebook/mcp_server.py` and the API client fallback with MCP configuration methods.
- Add read tools for discovery/list/profile.
- Add mutation tools for create/update/import/profile update.
- Preserve authenticated HTTP API behavior.

Acceptance:

- `open-notebook-mcp` can list configured MCP servers.
- An external agent session can discover and import local MCP servers through Open Notebook's MCP server.
- Mutating MCP configuration calls are auditable through normal Open Notebook API behavior.

### Slice 6: Live Runtime Setup

Work:

- Configure live runtime credentials for available AssemblyAI/OpenAI/ElevenLabs/Deepgram keys without printing secrets.
- Register chosen STT/TTS models.
- Set sensible defaults:
  - STT: AssemblyAI or OpenAI transcribe, with local Whisper-family fallback documented.
  - TTS: ElevenLabs or OpenAI TTS, depending configured key availability.
- Import local MCP servers from discovered runtime config.

Acceptance:

- Live `/api/models` includes STT/TTS model rows.
- Live `/api/models/defaults` has STT/TTS defaults when keys are present.
- Live `/api/mcp/servers` shows imported local MCP servers.
- Public route validation follows `docs/dev/runbooks/cooper-live-deployment.md`.

## Validation Plan

- Backend:
  - focused tests for provider metadata/discovery,
  - focused tests for MCP discovery/import,
  - `uv run ruff check .`.
- Frontend:
  - `npm run lint`,
  - `npm run build` for changed settings UX.
- Runtime:
  - authenticated API checks for providers, models, defaults, MCP servers,
  - browser check for settings page if frontend changes are included,
  - Cooper live deployment runbook for public-site changes.

## Risks And Open Decisions

- AssemblyAI execution uses an Open Notebook-owned STT adapter registered with Esperanto's provider map because the installed Esperanto version does not ship AssemblyAI STT.
- OpenAI Whisper-family can mean hosted `whisper-1`, hosted `gpt-4o-*transcribe`, local Python `whisper`, `whisper.cpp`, or `faster-whisper`; the UX should name these separately.
- Local MCP discovery must avoid returning secrets embedded in env blocks.
- Codex/OpenClaw config locations vary across local installs; discovery should be additive and transparent about searched paths.
- Mutating MCP configuration through MCP itself is powerful; defaults should keep import/update tools explicit and auditable.

## Execution Log

- 2026-06-22: Plan created from current Open Notebook source inspection, current OpenClaw docs, and live operator requirements.
- 2026-06-22: Slice 1 implemented. Added AssemblyAI provider metadata as STT-only, corrected Deepgram metadata to expose STT and TTS, added curated OpenAI audio discovery entries, and later added executable AssemblyAI STT support through an Open Notebook adapter.
- 2026-06-22: Slice 3 implemented. Added safe Codex-config local MCP discovery at `GET /api/mcp/discover-local` and import at `POST /api/mcp/import-local`, with env value redaction and already-imported detection by stable signature.
- 2026-06-22: Slice 4 implemented. Added frontend discovery/import panel to the existing Advanced MCP Servers card, and verified imported servers appear in the configured list and can be tested.
- 2026-06-22: Slice 5 implemented. Extended the first-party Open Notebook MCP server with MCP config discovery, import, create, update, test, delete, and Codex MCP profile tools backed by the authenticated HTTP API.
- 2026-06-22: Validation passed: `uv run pytest tests/test_credentials_api.py tests/test_models_api.py tests/test_mcp_client_config.py tests/test_mcp_server.py -q` passed with 41 tests; targeted `uv run ruff check ...` passed; `npm run lint` passed with 10 pre-existing warnings; `npm run build` passed.
- 2026-06-22: Added AssemblyAI env alias support for both `ASSEMBLYAI_API_KEY` and `ASSEMBLY_AI_API_KEY`.
- 2026-06-22: Local service probe against the mounted Codex home found 24 MCP candidates. The standalone probe also showed a local dev DB readback warning when SurrealDB was not available at the repo-default port; the discovery service now returns candidates with a warning instead of failing.
- 2026-06-22: Re-validation after alias/resilience changes passed: `uv run pytest tests/test_credentials_api.py tests/test_models_api.py tests/test_mcp_client_config.py tests/test_mcp_server.py -q` passed with 41 tests; targeted `uv run ruff check ...` passed.
- 2026-06-22: Added first-class HTTP and SSE MCP client support for tool inspection/calls. Local loopback HTTP MCP imports are rewritten for Docker runtime reachability with the original Host header preserved in metadata.
- 2026-06-22: Full backend validation passed: `uv run pytest tests/ -q` passed with 241 tests and two existing dependency warnings. Focused MCP validation passed with 19 tests. Docker image `open-notebook:cooper` rebuilt successfully.
- 2026-06-22: Live public route validation passed. `/config` returns `{"apiUrl":""}`. Provider readback shows `openai`, `elevenlabs`, `ollama`, and `codex_app_server` available; OpenAI exposes language, embedding, STT, and TTS; ElevenLabs exposes STT and TTS.
- 2026-06-22: Live model sync/default setup completed. OpenAI sync discovered 120 models, ElevenLabs sync discovered 6 models. Defaults now preserve Codex App Server for chat/tools and Ollama for embeddings, with `gpt-4o-mini-transcribe` as STT and `eleven_multilingual_v2` as TTS.
- 2026-06-22: Live local MCP discovery found 12 Codex-configured candidates. Imported and enabled Graphiti, Codegraph, and Codebase-Memory-MCP. Live tool tests passed: Graphiti exposes 24 tools over HTTP MCP, Codegraph exposes 10 tools over stdio MCP, and Codebase-Memory-MCP exposes 14 tools over stdio MCP.
- 2026-06-22: Live runtime key gap remains for AssemblyAI and Deepgram. The code supports AssemblyAI and Deepgram discovery metadata, but the Cooper runtime env currently has no `ASSEMBLYAI_API_KEY`, `ASSEMBLY_AI_API_KEY`, or `DEEPGRAM_API_KEY`.
- 2026-06-22: AssemblyAI moved from metadata-only to executable STT support. Added an Open Notebook AssemblyAI pre-recorded STT adapter, registered it with Esperanto's STT provider map, wired provider-key aliases through DB/env provisioning, added STT credential-test instantiation, and removed the realtime-only `universal-streaming` model from pre-recorded model discovery.
- 2026-06-22: Full backend validation after AssemblyAI adapter work passed: `uv run pytest tests/ -q` passed with 246 tests and two existing dependency warnings. Focused AssemblyAI/model/credential validation passed with 30 tests; targeted Ruff passed.
- 2026-06-22: Live image rebuilt and Cooper container restarted with the AssemblyAI adapter. In-container readback confirms `assemblyai` is registered in Esperanto's `speech_to_text` provider map. Public provider readback still shows AssemblyAI unavailable until a runtime key is supplied. Existing live defaults and imported MCP servers remained healthy after restart.
- 2026-06-22: Completed the audio defaults UX empty state. Default Model Assignments now shows a compact Audio Setup alert when STT/TTS defaults are missing or no registered model exists for either audio role. Frontend validation passed: `npm run lint` passed with 10 unrelated existing warnings and `npm run build` passed.
- 2026-06-22: Live image rebuilt and Cooper container restarted after the audio setup UX change. Public readback passed: `/config` returns `{"apiUrl":""}`, STT/TTS defaults remain set, local MCP discovery reports 12 candidates with Graphiti/Codegraph/Codebase-Memory-MCP imported, and live MCP tool tests still pass for Graphiti (24 tools), Codegraph (10 tools), and Codebase-Memory-MCP (14 tools).
- 2026-06-22: Final validation passed: `uv run ruff check .` passed, `git diff --check` passed, frontend lint/build passed, full backend tests passed, and live public API/MCP checks passed.
