# Plan 0004 | Local TTS Open Notebook Wiring

## Status

- State: complete
- Started: 2026-06-24
- Completed: 2026-06-24
- Owner: local operator / Codex
- Scope: Cooper live Open Notebook runtime and reusable repo support for local TTS model registration

## Goal

Wire the already-running local TTS services into Open Notebook so they are visible in Settings -> API Keys / Models, selectable as `text_to_speech` models, and eligible for `default_text_to_speech_model`.

## Pre-Execution Evidence

Local services are active as user services:

- `open-notebook-kokoro-tts.service`
- `open-notebook-dia-tts.service`
- `open-notebook-chatterbox-tts.service`
- `open-notebook-orpheus-tts.service`

OpenAI-compatible local TTS endpoints currently available:

- Kokoro: `http://127.0.0.1:18880/v1`, model `kokoro-82m`
- Chatterbox: `http://127.0.0.1:18882/v1`, model `chatterbox-tts`
- Orpheus: `http://127.0.0.1:18883/v1`, model `orpheus-3b`

Dia is currently exposed as a Gradio app:

- Dia UI: `http://127.0.0.1:18881/`
- Dia does not yet expose an OpenAI-compatible `/v1/audio/speech` endpoint from the current unit.

Live Open Notebook container state readback on 2026-06-24:

- Container: `open-notebook-cooper`
- App URL: `http://127.0.0.1:15055`
- Database `model` table: empty
- Database `credential` table: empty
- `open_notebook:default_models` has no TTS default
- Container env does not include `OPENAI_COMPATIBLE_BASE_URL_TTS`

Pre-execution conclusion: the local TTS services were installed and healthy beside Open Notebook, but were not yet registered inside Open Notebook.

## Result

Kokoro, Chatterbox, and Orpheus are now registered in the Cooper live Open
Notebook runtime as `openai_compatible` `text_to_speech` models. Kokoro is set
as `default_text_to_speech_model`.

Dia remains UI-only for Open Notebook model registration until it has an
OpenAI-compatible wrapper.

## Non-Goals

- Do not commit secrets, live auth files, generated audio, or Hugging Face cache contents.
- Do not make Dia a default Open Notebook TTS model until it has an OpenAI-compatible wrapper.
- Do not assume a commit or push updates the live site; live changes must follow the Cooper deployment/runbook path.
- Do not replace cloud TTS providers; local TTS should coexist with OpenAI, ElevenLabs, Deepgram, and other configured providers.

## Design

Use the existing Open Notebook model system rather than inventing a separate audio-provider layer:

- Provider: `openai_compatible`
- Type: `text_to_speech`
- Credential base URL fields:
  - Direct host runtime: `http://127.0.0.1:<port>/v1`
  - Docker/container runtime: `http://host.docker.internal:<port>/v1` if available
  - Linux Docker fallback: host-gateway alias or bridge-reachable host IP if `host.docker.internal` is unavailable
- Model records:
  - `kokoro-82m`
  - `chatterbox-tts`
  - `orpheus-3b`

The frontend should not need a new provider card for each local TTS service in the first slice. They can be represented as OpenAI-compatible credentials/models, with display names making the local service clear.

## Implementation Slices

### Slice 1: Live Runtime Registration

Work:

- Done: determined that `host.docker.internal` is reachable from `open-notebook-cooper` for ports `18880`, `18882`, and `18883`.
- Done: created OpenAI-compatible credentials for Kokoro, Chatterbox, and Orpheus using a non-secret local placeholder API key.
- Done: registered each service's model as `text_to_speech`.
- Done: set the default TTS model to Kokoro first, because it is the smallest and fastest local default.
- Done: kept Chatterbox and Orpheus available as selectable alternatives.

Acceptance:

- Live `credential` table has local TTS OpenAI-compatible entries.
- Live `model` table has `text_to_speech` rows for `kokoro-82m`, `chatterbox-tts`, and `orpheus-3b`.
- `GET /api/models/defaults` shows `default_text_to_speech_model` set to the selected local TTS model.
- Settings -> API Keys / Models shows local TTS choices under Default Model Assignments.

### Slice 2: Connectivity And Generation Smoke

Work:

- Done: from inside `open-notebook-cooper`, called each registered service's `/v1/models`.
- Done: ran a short Open Notebook model test for Kokoro, Chatterbox, and Orpheus.
- Done: generated audio through `ModelManager.get_text_to_speech()` using the default TTS model.

Acceptance:

- Container-to-service `/v1/models` checks pass for Kokoro, Chatterbox, and Orpheus.
- Open Notebook model tests pass or return a clearly documented product/runtime error.
- One generated audio artifact is created through the Open Notebook model path, or the blocker is recorded with logs and exact endpoint/config evidence.

### Slice 3: Repo-Owned Registration Helper

Work:

- Done: added `scripts/register_local_tts_models.py`.
- Done: kept host-specific URLs configurable through env vars.
- Done: avoided writing secrets to stdout.
- Done: updated `docs/5-CONFIGURATION/local-tts.md` with the supported registration flow.

Acceptance:

- A future live runtime can run one documented command to seed the local TTS credentials/models.
- Re-running the command does not duplicate records.
- The docs distinguish service installation from Open Notebook model registration.

### Slice 4: Dia OpenAI-Compatible Wrapper

Work:

- Pending follow-up: add or adapt a Dia wrapper that exposes:
  - `GET /health`
  - `GET /v1/models`
  - `POST /v1/audio/speech`
- Keep the Gradio UI available for inspection.
- Register Dia only after the wrapper passes local and container-reachable smoke tests.

Acceptance:

- Dia has an OpenAI-compatible endpoint parallel to the other local TTS services.
- Dia can be registered as a `text_to_speech` model.
- Dia appears as an optional default TTS choice.

### Slice 5: UX Polish

Work:

- Deferred: add a concise local TTS status panel or empty-state guidance if OpenAI-compatible TTS services are detected but not registered.
- Covered by existing UX data source: registered local TTS models are returned by `/api/models` and therefore available to the Default Model Assignments dropdowns.

Acceptance:

- A user visiting Settings -> API Keys can see whether local TTS is installed, registered, and defaulted.
- Missing local TTS registration has an actionable message.
- Registered local TTS models are clearly labeled and selectable.

## Validation Plan

Run validation in this order:

1. Done: `systemctl --user is-active` reports active for Kokoro, Dia, Chatterbox, and Orpheus.
2. Done: host-loopback checks pass for Kokoro, Chatterbox, Orpheus, and Dia UI.
3. Done: container-to-host `/v1/models` checks pass for Kokoro, Chatterbox, and Orpheus through `host.docker.internal`.
4. Done: app database readback shows three `text_to_speech` model records and three OpenAI-compatible local TTS credentials.
5. Done: authenticated Open Notebook API readback returns the three TTS models and `default_text_to_speech_model=model:u4xmp1r8skkxytnyd0i2`.
6. Covered indirectly: the Settings page uses `/api/models` and `/api/models/defaults`, both of which now return the local TTS models/default. A browser screenshot was not captured in this slice.
7. Done: `python3 -m py_compile` and `uv run ruff check` pass for the registration helper and touched wrappers.
8. Not run: no frontend code changed in this slice.

## Execution Evidence

- Registered credentials:
  - `Local Kokoro TTS`: `http://host.docker.internal:18880/v1`
  - `Local Chatterbox TTS`: `http://host.docker.internal:18882/v1`
  - `Local Orpheus TTS`: `http://host.docker.internal:18883/v1`
- Registered models:
  - `kokoro-82m`: `model:u4xmp1r8skkxytnyd0i2`
  - `chatterbox-tts`: `model:i3qtgcuca8pixntkr2u7`
  - `orpheus-3b`: `model:w8xniz6pqzub1r4mgfen`
- Default TTS:
  - `default_text_to_speech_model`: `model:u4xmp1r8skkxytnyd0i2`
- Open Notebook model tests:
  - `kokoro-82m`: speech generation successful.
  - `chatterbox-tts`: speech generation successful after adding `mp3` response-format compatibility.
  - `orpheus-3b`: speech generation successful after adding `mp3` response-format compatibility and OpenAI voice aliases.
- Default TTS smoke:
  - `ModelManager.get_text_to_speech()` returned `OpenAICompatibleTextToSpeechModel`.
  - `agenerate_speech(text='Default local TTS smoke test.', voice='alloy')` returned an `AudioResponse` with `audio_data` size `17208` bytes, content type `audio/mp3`, model `kokoro-82m`.

## Risks

- Docker may not resolve `host.docker.internal` on this Linux host unless an extra host-gateway mapping exists.
- Chatterbox and Orpheus are GPU-heavy; concurrent use with Dia may require operational guidance or service pause/start workflows.
- Esperanto's OpenAI-compatible TTS adapter may assume OpenAI-specific voices or request fields that local wrappers must tolerate.
- Dia requires wrapper work before it can participate in model defaults.
- The live app requires authentication, so validation should prefer app-local repository readback or authenticated browser/API checks.

## Definition Of Done

- Kokoro, Chatterbox, and Orpheus are registered in the live Open Notebook runtime as `text_to_speech` models.
- Kokoro is set as the initial default local TTS model unless a smoke test proves a better default.
- Settings -> API Keys / Models shows non-empty TTS choices.
- The service installation docs explain the second step: register the running service with Open Notebook.
- Dia status is explicit: either registered through a wrapper or documented as UI-only pending wrapper work.
