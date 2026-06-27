# Local Text-to-Speech Setup

Run text-to-speech locally for free, private podcast generation using OpenAI-compatible TTS servers.

---

## Why Local TTS?

| Benefit | Description |
|---------|-------------|
| **Free** | No per-character costs after setup |
| **Private** | Audio never leaves your machine |
| **Unlimited** | No rate limits or quotas |
| **Offline** | Works without internet |

---

## Quick Start with Speaches

[Speaches](https://github.com/speaches-ai/speaches) is an open-source, OpenAI-compatible TTS server.

> **💡 Ready-made Docker Compose files available:**
> - **[docker-compose-speaches.yml](../../examples/docker-compose-speaches.yml)** - Speaches + Open Notebook
> - **[docker-compose-full-local.yml](../../examples/docker-compose-full-local.yml)** - Speaches + Ollama (100% local setup)
>
> These include complete setup instructions and configuration examples. Just copy and run!

### Step 1: Create Docker Compose File

Create a folder and add `docker-compose.yml`:

```yaml
services:
  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cpu
    container_name: speaches
    ports:
      - "8969:8000"
    volumes:
      - hf-hub-cache:/home/ubuntu/.cache/huggingface/hub
    restart: unless-stopped

volumes:
  hf-hub-cache:
```

### Step 2: Start and Download Model

```bash
# Start Speaches
docker compose up -d

# Wait for startup
sleep 10

# Download voice model (~500MB)
docker compose exec speaches uv tool run speaches-cli model download speaches-ai/Kokoro-82M-v1.0-ONNX
```

### Step 3: Test

```bash
curl "http://localhost:8969/v1/audio/speech" -s \
  -H "Content-Type: application/json" \
  --output test.mp3 \
  --data '{
    "input": "Hello! Local TTS is working.",
    "model": "speaches-ai/Kokoro-82M-v1.0-ONNX",
    "voice": "af_bella"
  }'
```

Play `test.mp3` to verify.

### Step 4: Configure Open Notebook

**Via Settings UI (Recommended):**
1. Go to **Settings** → **API Keys**
2. Click **Add Credential** → Select **OpenAI-Compatible**
3. Enter base URL for TTS: `http://host.docker.internal:8969/v1` (Docker) or `http://localhost:8969/v1` (local)
4. Click **Save**, then **Test Connection**

**Legacy (Deprecated) — Environment variables:**
```yaml
# In your Open Notebook docker-compose.yml
environment:
  - OPENAI_COMPATIBLE_BASE_URL_TTS=http://host.docker.internal:8969/v1
```

```bash
# Local development
export OPENAI_COMPATIBLE_BASE_URL_TTS=http://localhost:8969/v1
```

### Step 5: Add Model in Open Notebook

1. Go to **Settings** → **Models**
2. Click **Add Model** in Text-to-Speech section
3. Configure:
   - **Provider**: `openai_compatible`
   - **Model Name**: `speaches-ai/Kokoro-82M-v1.0-ONNX`
   - **Display Name**: `Local TTS`
4. Click **Save**
5. Set as default if desired

---

## Built-in Kokoro Runtime Wrapper

Open Notebook also ships a small optional Kokoro runtime wrapper under
[`scripts/local_tts/kokoro_openai_server.py`](../../scripts/local_tts/kokoro_openai_server.py).
It is useful when you want a tiny local ONNX-backed TTS service with both an
OpenAI-compatible API and a browser UI for inspection.

The wrapper exposes:

- `GET /` browser UI for text entry, voice selection, speed, playback, and WAV download
- `GET /docs` FastAPI API inspector
- `GET /v1/models`
- `GET /v1/audio/voices`
- `POST /v1/audio/speech`

Run it with `uvicorn` after installing `kokoro-onnx` and placing the ONNX model
and voices file under a user-scoped runtime directory. See
[`scripts/local_tts/README.md`](../../scripts/local_tts/README.md) for install,
environment, and service details.

Example OpenAI-compatible base URLs:

```text
http://host.docker.internal:18880/v1  # Open Notebook in Docker
http://127.0.0.1:18880/v1            # Open Notebook on the same host
```

## Optional Chatterbox and Orpheus Wrappers

The same `scripts/local_tts/` directory also includes optional local wrappers
for heavier expressive TTS backends:

- [`chatterbox_openai_server.py`](../../scripts/local_tts/chatterbox_openai_server.py)
  for Resemble AI Chatterbox. It includes a browser UI, OpenAI-compatible
  speech endpoint, and optional voice prompt upload.
- [`orpheus_openai_server.py`](../../scripts/local_tts/orpheus_openai_server.py)
  for Orpheus. It includes a browser UI, OpenAI-compatible speech endpoint, and
  voice selection for the Orpheus voices exposed by the package.

Suggested local ports:

```text
Kokoro:     http://host.docker.internal:18880/v1
Chatterbox: http://host.docker.internal:18882/v1
Orpheus:    http://host.docker.internal:18883/v1
Dia API:    http://host.docker.internal:18884/v1
```

### Register Local TTS Models In Open Notebook

Starting a local TTS service is only the first step. Open Notebook also needs
`openai_compatible` credential and model records before the service appears in
Settings -> API Keys / Models or in Default Model Assignments.

Use the repo-owned registration helper from an Open Notebook runtime
environment:

```bash
uv run python scripts/register_local_tts_models.py
```

For the Cooper Docker deployment, run the helper inside the live app container:

```bash
docker exec -i open-notebook-cooper /app/.venv/bin/python /app/scripts/register_local_tts_models.py
```

By default the helper registers:

| Service | Model | Base URL |
| --- | --- | --- |
| Kokoro | `kokoro-82m` | `http://host.docker.internal:18880/v1` |
| Chatterbox | `chatterbox-tts` | `http://host.docker.internal:18882/v1` |
| Orpheus | `orpheus-3b` | `http://host.docker.internal:18883/v1` |

It also sets `kokoro-82m` as `default_text_to_speech_model`. Override service
URLs or the default model with environment variables:

```bash
OPEN_NOTEBOOK_LOCAL_TTS_KOKORO_URL=http://127.0.0.1:18880/v1 \
OPEN_NOTEBOOK_LOCAL_TTS_CHATTERBOX_URL=http://127.0.0.1:18882/v1 \
OPEN_NOTEBOOK_LOCAL_TTS_ORPHEUS_URL=http://127.0.0.1:18883/v1 \
OPEN_NOTEBOOK_LOCAL_TTS_DEFAULT=orpheus-3b \
uv run python scripts/register_local_tts_models.py
```

Dia is opt-in because it needs the separate OpenAI-compatible wrapper on port
`18884`, while the Gradio UI remains on port `18881`:

```bash
OPEN_NOTEBOOK_LOCAL_TTS_DIA_URL=http://host.docker.internal:18884/v1 \
uv run python scripts/register_local_tts_models.py --include-dia
```

Dia can condition generation on an uploaded voice sample. Upstream Dia expects
the transcript of that sample before the text to generate. The local wrapper
keeps manual transcript entry available, but it can also call Open Notebook's
configured default speech-to-text model to fill the transcript automatically.

Configure the wrapper service with:

```bash
DIA_TRANSCRIPTION_URL=http://127.0.0.1:5055/api/audio/transcriptions
DIA_TRANSCRIPTION_AUTH_BEARER=<open-notebook-password>
```

The Open Notebook endpoint is:

```text
POST /api/audio/transcriptions
```

It accepts multipart form data with `file`, optional `language`, and optional
`prompt`, then returns the transcription from `default_speech_to_text_model`.
The Dia wrapper exposes the same convenience at `/v1/audio/transcriptions` and
uses it automatically from `/v1/audio/speech-form` when a voice sample is
uploaded without a transcript. The wrapper clips uploaded voice samples to
`DIA_AUDIO_PROMPT_MAX_SECONDS`, defaulting to 10 seconds, before generation.
This keeps Dia inside its fixed decoder prefill window and reserves at least
`DIA_AUDIO_PROMPT_MIN_GENERATION_TOKENS`, defaulting to 128, for generated
speech. Use short 5-10 second reference samples for reliable voice
conditioning.

On the Cooper WSL deployment these are exposed for inspection as:

```text
Kokoro:     https://kokoro.ecochran.dyndns.org/
Dia:        https://dia.ecochran.dyndns.org/
Chatterbox: https://chatterbox.ecochran.dyndns.org/
Orpheus:    https://orpheus.ecochran.dyndns.org/
```

These wrappers are intended for local operators. Keep model weights, Hugging
Face cache, generated audio, and service files outside the repo. See
[`scripts/local_tts/README.md`](../../scripts/local_tts/README.md) for runtime
commands and environment variables.

---

## Available Voices

The Kokoro model includes multiple voices:

### Female Voices
| Voice ID | Description |
|----------|-------------|
| `af_bella` | Clear, professional |
| `af_sarah` | Warm, friendly |
| `af_nicole` | Energetic, expressive |

### Male Voices
| Voice ID | Description |
|----------|-------------|
| `am_adam` | Deep, authoritative |
| `am_michael` | Friendly, conversational |

### British Accents
| Voice ID | Description |
|----------|-------------|
| `bf_emma` | British female, professional |
| `bm_george` | British male, formal |

### Test Different Voices

```bash
for voice in af_bella af_sarah am_adam am_michael; do
  curl "http://localhost:8969/v1/audio/speech" -s \
    -H "Content-Type: application/json" \
    --output "test_${voice}.mp3" \
    --data "{
      \"input\": \"Hello, this is the ${voice} voice.\",
      \"model\": \"speaches-ai/Kokoro-82M-v1.0-ONNX\",
      \"voice\": \"${voice}\"
    }"
done
```

---

## GPU Acceleration

For faster generation with NVIDIA GPUs:

```yaml
services:
  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cuda
    container_name: speaches
    ports:
      - "8969:8000"
    volumes:
      - hf-hub-cache:/home/ubuntu/.cache/huggingface/hub
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  hf-hub-cache:
```

---

## Docker Networking

When configuring your OpenAI-Compatible credential in **Settings → API Keys**, use the appropriate TTS base URL for your setup:

### Open Notebook in Docker (macOS/Windows)

**TTS Base URL:** `http://host.docker.internal:8969/v1`

### Open Notebook in Docker (Linux)

**TTS Base URL (Option 1 — Docker bridge IP):** `http://172.17.0.1:8969/v1`

**Option 2:** Use host networking mode (`docker run --network host ...`), then use: `http://localhost:8969/v1`

### Remote Server

Run Speaches on a different machine:

**TTS Base URL:** `http://server-ip:8969/v1` (replace with your server's IP)

---

## Multi-Speaker Podcasts

Configure different voices for each speaker:

```
Speaker 1 (Host):
  Model: speaches-ai/Kokoro-82M-v1.0-ONNX
  Voice: af_bella

Speaker 2 (Guest):
  Model: speaches-ai/Kokoro-82M-v1.0-ONNX
  Voice: am_adam

Speaker 3 (Narrator):
  Model: speaches-ai/Kokoro-82M-v1.0-ONNX
  Voice: bf_emma
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs speaches

# Verify port available
lsof -i :8969

# Restart
docker compose down && docker compose up -d
```

### Connection Refused

```bash
# Test Speaches is running
curl http://localhost:8969/v1/models

# From inside Open Notebook container
docker exec -it open-notebook curl http://host.docker.internal:8969/v1/models
```

### Model Not Found

```bash
# List downloaded models
docker compose exec speaches uv tool run speaches-cli model list

# Download if missing
docker compose exec speaches uv tool run speaches-cli model download speaches-ai/Kokoro-82M-v1.0-ONNX
```

### Poor Audio Quality

- Try different voices
- Adjust speed: `"speed": 0.9` to `1.2`
- Check model downloaded completely
- Allocate more memory

### Slow Generation

| Solution | How |
|----------|-----|
| Use GPU | Switch to `latest-cuda` image |
| More CPU | Allocate more cores in Docker |
| Faster model | Use smaller/quantized models |
| SSD storage | Move Docker volumes to SSD |

---

## Performance Tips

### Recommended Specs

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 4+ GB |
| Storage | 5 GB | 10 GB (for multiple models) |
| GPU | None | NVIDIA (optional) |

### Resource Limits

```yaml
services:
  speaches:
    # ... other config
    mem_limit: 4g
    cpus: 2
```

### Monitor Usage

```bash
docker stats speaches
```

---

## Comparison: Local vs Cloud

| Aspect | Local (Speaches) | Cloud (OpenAI/ElevenLabs) |
|--------|------------------|---------------------------|
| **Cost** | Free | $0.015-0.10/min |
| **Privacy** | Complete | Data sent to provider |
| **Speed** | Depends on hardware | Usually faster |
| **Quality** | Good | Excellent |
| **Setup** | Moderate | Simple API key |
| **Offline** | Yes | No |
| **Voices** | Limited | Many options |

### When to Use Local

- Privacy-sensitive content
- High-volume generation
- Development/testing
- Offline environments
- Cost control

### When to Use Cloud

- Premium quality needs
- Multiple languages
- Time-sensitive projects
- Limited hardware

---

## Other Local TTS Options

Any OpenAI-compatible TTS server works. The key is:

1. Server implements `/v1/audio/speech` endpoint
2. Add an OpenAI-Compatible credential in **Settings → API Keys** with the TTS base URL
3. Add model with provider `openai_compatible`

---

## Related

- **[Local STT Setup](local-stt.md)** - Speech-to-text with Speaches
- **[OpenAI-Compatible Providers](openai-compatible.md)** - General compatible provider setup
- **[AI Providers](ai-providers.md)** - All provider configuration
- **[Creating Podcasts](../3-USER-GUIDE/creating-podcasts.md)** - Using TTS for podcasts
