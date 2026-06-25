# Local TTS Runtime Scripts

These scripts are optional local runtime helpers for operators who want
OpenAI-compatible speech services alongside Open Notebook. They are not part of
the Open Notebook API process and should keep model weights, caches, generated
audio, and credentials outside the repo.

## Kokoro OpenAI-Compatible Server

`kokoro_openai_server.py` wraps `kokoro-onnx` with:

- `GET /` browser UI for text entry, voice selection, speed, playback, and WAV download
- `GET /health`
- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/speech`
- `GET /docs` FastAPI API inspector

Install a local runtime:

```bash
uv venv ~/.local/share/open-notebook/tts/kokoro/.venv --python 3.12
uv pip install --python ~/.local/share/open-notebook/tts/kokoro/.venv/bin/python \
  kokoro-onnx soundfile fastapi uvicorn python-multipart huggingface-hub numpy
```

Place model assets outside the repo:

```text
~/.local/share/open-notebook/tts/kokoro/models/kokoro-v1.0.onnx
~/.local/share/open-notebook/tts/kokoro/models/voices-v1.0.bin
```

Run locally:

```bash
KOKORO_TTS_ROOT="$HOME/.local/share/open-notebook/tts/kokoro" \
~/.local/share/open-notebook/tts/kokoro/.venv/bin/python -m uvicorn \
  scripts.local_tts.kokoro_openai_server:app \
  --host 127.0.0.1 \
  --port 18880
```

Useful environment variables:

| Variable | Default |
| --- | --- |
| `KOKORO_TTS_ROOT` | `~/.local/share/open-notebook/tts/kokoro` |
| `KOKORO_MODEL_PATH` | `$KOKORO_TTS_ROOT/models/kokoro-v1.0.onnx` |
| `KOKORO_VOICES_PATH` | `$KOKORO_TTS_ROOT/models/voices-v1.0.bin` |
| `KOKORO_DEFAULT_VOICE` | `af_bella` |
| `KOKORO_OPENAI_MODEL` | `kokoro-82m` |

Configure Open Notebook as an OpenAI-compatible TTS provider with the base URL:

```text
http://host.docker.internal:18880/v1
```

Use `http://127.0.0.1:18880/v1` when Open Notebook is running directly on the
same host instead of inside Docker.

## Chatterbox OpenAI-Compatible Server

`chatterbox_openai_server.py` wraps Resemble AI Chatterbox with:

- `GET /` browser UI for text entry, optional voice prompt upload, playback, and WAV download
- `GET /health`
- `GET /v1/models`
- `POST /v1/audio/speech`
- `POST /v1/audio/speech-form` for browser uploads

Run it from a Chatterbox virtualenv:

```bash
CHATTERBOX_TTS_ROOT="$HOME/.local/share/open-notebook/tts/chatterbox" \
~/.local/share/open-notebook/tts/chatterbox/.venv/bin/python -m uvicorn \
  scripts.local_tts.chatterbox_openai_server:app \
  --host 127.0.0.1 \
  --port 18882
```

Useful environment variables:

| Variable | Default |
| --- | --- |
| `CHATTERBOX_TTS_ROOT` | `~/.local/share/open-notebook/tts/chatterbox` |
| `CHATTERBOX_OPENAI_MODEL` | `chatterbox-tts` |
| `CHATTERBOX_DEVICE` | `cuda` when available, otherwise `cpu` |

Configure Open Notebook with:

```text
http://host.docker.internal:18882/v1
```

On the Cooper WSL host this service is pinned to user systemd unit
`open-notebook-chatterbox-tts.service`, local URL
`http://chatterbox.localhost/`, and Authelia-protected public URL
`https://chatterbox.ecochran.dyndns.org/`.

## Orpheus OpenAI-Compatible Server

`orpheus_openai_server.py` wraps `orpheus-speech` with:

- `GET /` browser UI for text entry, voice selection, playback, and WAV download
- `GET /health`
- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/speech`

Run it from an Orpheus virtualenv:

```bash
~/.local/share/open-notebook/tts/orpheus/.venv/bin/python -m uvicorn \
  scripts.local_tts.orpheus_openai_server:app \
  --host 127.0.0.1 \
  --port 18883
```

Useful environment variables:

| Variable | Default |
| --- | --- |
| `ORPHEUS_OPENAI_MODEL` | `orpheus-3b` |
| `ORPHEUS_MODEL_NAME` | `canopylabs/orpheus-tts-0.1-finetune-prod` |
| `ORPHEUS_DTYPE` | `bfloat16` |
| `ORPHEUS_SAMPLE_RATE` | `24000` |
| `ORPHEUS_DEFAULT_VOICE` | `zoe` |

Configure Open Notebook with:

```text
http://host.docker.internal:18883/v1
```

On the Cooper WSL host this service is pinned to user systemd unit
`open-notebook-orpheus-tts.service`, local URL `http://orpheus.localhost/`, and
Authelia-protected public URL `https://orpheus.ecochran.dyndns.org/`.

Orpheus initializes a vLLM engine and is substantially heavier than Kokoro.
The wrapper lazy-loads the model on first generation so health/UI routes are
available before model initialization. The default upstream model is gated on
Hugging Face, so speech generation requires a valid token with access.

## Dia OpenAI-Compatible Server

`dia_openai_server.py` wraps the local Dia runtime with:

- `GET /` browser UI for text entry, optional voice sample upload, sample transcription, generation controls, playback, and WAV download
- `GET /health`
- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/transcriptions`
- `POST /v1/audio/speech`
- `POST /v1/audio/speech-form`

Dia is dialogue-oriented. Inputs that already contain `[S1]` or `[S2]` are
passed through unchanged; plain text is wrapped as a single speaker. OpenAI
voice names are treated as prompt aliases, not distinct trained voices.

Run it from the Dia virtualenv:

```bash
~/.local/share/open-notebook/tts/dia/.venv/bin/python -m uvicorn \
  scripts.local_tts.dia_openai_server:app \
  --host 127.0.0.1 \
  --port 18884
```

Useful environment variables:

| Variable | Default |
| --- | --- |
| `DIA_OPENAI_MODEL` | `dia-1.6b` |
| `DIA_MODEL_NAME` | `nari-labs/Dia-1.6B-0626` |
| `DIA_DEVICE` | `cuda` when available, otherwise `cpu` |
| `DIA_COMPUTE_DTYPE` | `float16` on CUDA, otherwise `float32` |
| `DIA_SAMPLE_RATE` | `44100` |
| `DIA_DEFAULT_VOICE` | `dialogue` |
| `DIA_MAX_TOKENS` | `860` |
| `DIA_TRANSCRIPTION_URL` | unset |
| `DIA_TRANSCRIPTION_AUTH_BEARER` | `OPEN_NOTEBOOK_PASSWORD` when set |
| `DIA_TRANSCRIPTION_TIMEOUT` | `600` |

Dia voice prompting requires the transcript for the uploaded sample. When
`DIA_TRANSCRIPTION_URL` points at Open Notebook's `/api/audio/transcriptions`
endpoint, the wrapper can transcribe the uploaded sample with the configured
default speech-to-text model and prepend that transcript to the Dia prompt.

Example for the Cooper container:

```bash
DIA_TRANSCRIPTION_URL=http://127.0.0.1:5055/api/audio/transcriptions
```

If Open Notebook password auth is enabled, set `DIA_TRANSCRIPTION_AUTH_BEARER`
to the same bearer token. Operators may still paste or edit the transcript
manually; the automatic path is just a convenience over the same Dia contract.

Configure Open Notebook with:

```text
http://host.docker.internal:18884/v1
```

Register Dia after the wrapper is running and reachable:

```bash
docker exec -i open-notebook-cooper /app/.venv/bin/python \
  /tmp/register_local_tts_models.py --include-dia
```
