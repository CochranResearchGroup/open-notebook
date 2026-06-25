#!/usr/bin/env python3
"""Small OpenAI-compatible Kokoro TTS server with a browser UI.

This wrapper is intended for local operator deployments. It keeps model files
outside the repo while making the runtime service reproducible.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Literal

import soundfile as sf
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from kokoro_onnx import Kokoro
from pydantic import BaseModel, Field

ROOT = Path(
    os.environ.get(
        "KOKORO_TTS_ROOT",
        Path.home() / ".local/share/open-notebook/tts/kokoro",
    )
)
MODEL_PATH = Path(os.environ.get("KOKORO_MODEL_PATH", ROOT / "models/kokoro-v1.0.onnx"))
VOICES_PATH = Path(os.environ.get("KOKORO_VOICES_PATH", ROOT / "models/voices-v1.0.bin"))
DEFAULT_VOICE = os.environ.get("KOKORO_DEFAULT_VOICE", "af_bella")
SERVICE_MODEL_ID = os.environ.get("KOKORO_OPENAI_MODEL", "kokoro-82m")

OPENAI_VOICE_ALIASES = {
    "alloy": "af_bella",
    "ash": "am_adam",
    "ballad": "am_michael",
    "coral": "af_sarah",
    "echo": "am_eric",
    "fable": "bf_emma",
    "nova": "af_nicole",
    "onyx": "am_adam",
    "sage": "af_sky",
    "shimmer": "af_bella",
}

app = FastAPI(title="Kokoro OpenAI-compatible TTS")
kokoro: Kokoro | None = None


class SpeechRequest(BaseModel):
    model: str = Field(default=SERVICE_MODEL_ID)
    input: str
    voice: str = Field(default=DEFAULT_VOICE)
    response_format: Literal["wav", "mp3", "opus", "aac", "flac", "pcm"] = "wav"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)


def _ui_html() -> str:
    model_id = json.dumps(SERVICE_MODEL_ID)
    default_voice = json.dumps(DEFAULT_VOICE)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kokoro TTS</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #202124;
      --muted: #63665f;
      --line: #d9ddd4;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --error: #b42318;
      --shadow: 0 14px 32px rgba(36, 40, 36, 0.10);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #121412;
        --panel: #1b1e1b;
        --text: #f1f5f2;
        --muted: #b7beb7;
        --line: #343a34;
        --accent: #5eead4;
        --accent-strong: #99f6e4;
        --error: #f97066;
        --shadow: 0 14px 32px rgba(0, 0, 0, 0.28);
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(980px, calc(100vw - 32px));
      margin: 32px auto;
    }}
    header {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 28px;
      line-height: 1.15;
      font-weight: 720;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .links {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    a {{
      color: var(--accent-strong);
      text-decoration: none;
    }}
    .link-button {{
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 8px 10px;
      background: var(--panel);
      color: var(--text);
      font-size: 13px;
    }}
    .surface {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    label {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    textarea, select, input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: color-mix(in srgb, var(--panel), var(--bg) 28%);
      color: var(--text);
      font: inherit;
    }}
    textarea {{
      min-height: 180px;
      resize: vertical;
      padding: 12px;
      line-height: 1.45;
    }}
    select {{
      height: 40px;
      padding: 0 10px;
    }}
    input[type="range"] {{
      accent-color: var(--accent);
    }}
    .controls {{
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(160px, 220px) minmax(120px, 160px);
      gap: 14px;
      margin: 16px 0;
      align-items: end;
    }}
    .speed-readout {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 48px;
      color: var(--text);
      font-size: 13px;
      margin-left: 8px;
    }}
    button {{
      appearance: none;
      height: 42px;
      border: 1px solid var(--accent);
      border-radius: 7px;
      background: var(--accent);
      color: #ffffff;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }}
    button:disabled {{
      cursor: wait;
      opacity: 0.7;
    }}
    .output {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }}
    audio {{
      width: 100%;
      min-width: 0;
    }}
    .download {{
      display: none;
      white-space: nowrap;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 9px 12px;
      color: var(--text);
    }}
    .status {{
      min-height: 22px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    .status.error {{
      color: var(--error);
    }}
    @media (max-width: 720px) {{
      main {{ width: min(100vw - 20px, 980px); margin-top: 16px; }}
      header, .output {{ display: block; }}
      .links {{ justify-content: flex-start; margin-top: 12px; }}
      .controls {{ grid-template-columns: 1fr; }}
      .download {{ display: none; margin-top: 10px; text-align: center; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Kokoro TTS</h1>
        <p class="subtitle">Local Kokoro 82M ONNX speech generation</p>
      </div>
      <nav class="links" aria-label="Service links">
        <a class="link-button" href="/docs">API Docs</a>
        <a class="link-button" href="/v1/audio/voices">Voices JSON</a>
        <a class="link-button" href="/health">Health</a>
      </nav>
    </header>
    <section class="surface">
      <label for="text">Text</label>
      <textarea id="text">Kokoro is running locally and ready for fast text to speech.</textarea>
      <div class="controls">
        <div>
          <label for="voice">Voice</label>
          <select id="voice"></select>
        </div>
        <div>
          <label for="speed">Speed <span id="speedValue" class="speed-readout">1.00x</span></label>
          <input id="speed" type="range" min="0.5" max="2" value="1" step="0.05">
        </div>
        <button id="generate" type="button">Generate</button>
      </div>
      <div class="output">
        <audio id="audio" controls></audio>
        <a id="download" class="download" download="kokoro.wav">Download WAV</a>
      </div>
      <div id="status" class="status" role="status"></div>
    </section>
  </main>
  <script>
    const modelId = {model_id};
    const defaultVoice = {default_voice};
    const voiceSelect = document.getElementById("voice");
    const speed = document.getElementById("speed");
    const speedValue = document.getElementById("speedValue");
    const text = document.getElementById("text");
    const audio = document.getElementById("audio");
    const generate = document.getElementById("generate");
    const download = document.getElementById("download");
    const status = document.getElementById("status");
    let currentObjectUrl = null;

    function setStatus(message, isError = false) {{
      status.textContent = message;
      status.classList.toggle("error", isError);
    }}

    function setSpeedLabel() {{
      speedValue.textContent = `${{Number(speed.value).toFixed(2)}}x`;
    }}

    async function loadVoices() {{
      const response = await fetch("/v1/audio/voices");
      if (!response.ok) throw new Error(`Voice list failed: ${{response.status}}`);
      const data = await response.json();
      voiceSelect.innerHTML = "";
      for (const voice of data.voices || []) {{
        const option = document.createElement("option");
        option.value = voice;
        option.textContent = voice;
        if (voice === (data.default || defaultVoice)) option.selected = true;
        voiceSelect.appendChild(option);
      }}
    }}

    async function generateSpeech() {{
      const input = text.value.trim();
      if (!input) {{
        setStatus("Enter text before generating audio.", true);
        return;
      }}
      generate.disabled = true;
      setStatus("Generating audio...");
      try {{
        const response = await fetch("/v1/audio/speech", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            model: modelId,
            input,
            voice: voiceSelect.value || defaultVoice,
            speed: Number(speed.value),
            response_format: "wav"
          }})
        }});
        if (!response.ok) {{
          const detail = await response.text();
          throw new Error(detail || `Speech request failed: ${{response.status}}`);
        }}
        const blob = await response.blob();
        if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
        currentObjectUrl = URL.createObjectURL(blob);
        audio.src = currentObjectUrl;
        download.href = currentObjectUrl;
        download.style.display = "inline-flex";
        setStatus(`Generated ${{Math.round(blob.size / 1024)}} KB WAV.`);
      }} catch (error) {{
        setStatus(error.message || String(error), true);
      }} finally {{
        generate.disabled = false;
      }}
    }}

    speed.addEventListener("input", setSpeedLabel);
    generate.addEventListener("click", generateSpeech);
    text.addEventListener("keydown", (event) => {{
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {{
        event.preventDefault();
        generateSpeech();
      }}
    }});

    setSpeedLabel();
    loadVoices().then(() => setStatus("Ready.")).catch((error) => setStatus(error.message, true));
  </script>
</body>
</html>
"""


@app.on_event("startup")
def load_model() -> None:
    global kokoro
    kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse(_ui_html())


@app.head("/")
def ui_head() -> Response:
    return Response(status_code=200)


@app.get("/health")
def health() -> dict[str, object]:
    voices = kokoro.get_voices() if kokoro else []
    return {
        "ok": kokoro is not None,
        "model": SERVICE_MODEL_ID,
        "voice_count": len(voices),
        "default_voice": DEFAULT_VOICE,
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": SERVICE_MODEL_ID,
                "object": "model",
                "owned_by": "local-kokoro",
            }
        ],
    }


@app.get("/v1/audio/voices")
def voices() -> dict[str, object]:
    if kokoro is None:
        raise HTTPException(status_code=503, detail="Kokoro model is still loading")
    return {"voices": kokoro.get_voices(), "default": DEFAULT_VOICE}


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest) -> Response:
    if kokoro is None:
        raise HTTPException(status_code=503, detail="Kokoro model is still loading")
    if request.model != SERVICE_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {request.model}")
    if not request.input.strip():
        raise HTTPException(status_code=400, detail="Input text is required")

    available_voices = set(kokoro.get_voices())
    voice = OPENAI_VOICE_ALIASES.get(request.voice, request.voice)
    if voice not in available_voices:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice: {request.voice}. Use /v1/audio/voices for available voices.",
        )

    audio, sample_rate = kokoro.create(request.input, voice=voice, speed=request.speed, lang="en-us")
    buffer = io.BytesIO()
    if request.response_format == "pcm":
        buffer.write(audio.astype("float32").tobytes())
        media_type = "application/octet-stream"
    else:
        sf.write(buffer, audio, sample_rate, format=request.response_format.upper())
        media_type = {
            "wav": "audio/wav",
            "flac": "audio/flac",
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "aac": "audio/aac",
        }.get(request.response_format, "audio/wav")
    return Response(content=buffer.getvalue(), media_type=media_type)
