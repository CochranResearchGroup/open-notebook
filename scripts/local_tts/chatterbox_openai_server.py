#!/usr/bin/env python3
"""OpenAI-compatible Chatterbox TTS server with a small browser UI."""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

import soundfile as sf
import torch
from chatterbox.tts import ChatterboxTTS
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

ROOT = Path(
    os.environ.get(
        "CHATTERBOX_TTS_ROOT",
        Path.home() / ".local/share/open-notebook/tts/chatterbox",
    )
)
SERVICE_MODEL_ID = os.environ.get("CHATTERBOX_OPENAI_MODEL", "chatterbox-tts")
DEVICE = os.environ.get("CHATTERBOX_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")

app = FastAPI(title="Chatterbox OpenAI-compatible TTS")
model: ChatterboxTTS | None = None
model_load_error: str | None = None


class SpeechRequest(BaseModel):
    model: str = Field(default=SERVICE_MODEL_ID)
    input: str
    voice: str = Field(default="default")
    response_format: Literal["wav", "mp3", "flac", "pcm"] = "wav"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    exaggeration: float = Field(default=0.5, ge=0.0, le=2.0)
    cfg_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    temperature: float = Field(default=0.8, ge=0.05, le=2.0)
    top_p: float = Field(default=1.0, ge=0.05, le=1.0)


def _audio_response(audio, sample_rate: int, response_format: str) -> Response:
    buffer = io.BytesIO()
    audio = audio.squeeze()
    if response_format == "pcm":
        buffer.write(audio.astype("float32").tobytes())
        media_type = "application/octet-stream"
    else:
        sf.write(buffer, audio, sample_rate, format=response_format.upper())
        media_type = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "flac": "audio/flac",
        }.get(response_format, "audio/wav")
    return Response(content=buffer.getvalue(), media_type=media_type)


def _ui_html() -> str:
    model_id = json.dumps(SERVICE_MODEL_ID)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Chatterbox TTS</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f6f6f3; --panel:#fff; --text:#202124; --muted:#62665f; --line:#d9ddd4; --accent:#2563eb; --error:#b42318; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#121417; --panel:#1b1f24; --text:#f3f5f7; --muted:#b6bec8; --line:#343a42; --accent:#60a5fa; --error:#f97066; }} }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ width:min(980px, calc(100vw - 32px)); margin:32px auto; }}
    header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:18px; }}
    h1 {{ margin:0 0 4px; font-size:28px; line-height:1.15; letter-spacing:0; }}
    .subtitle, label, .status {{ color:var(--muted); font-size:13px; }}
    .surface {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 14px 32px rgba(20,24,20,.10); }}
    textarea, input {{ width:100%; border:1px solid var(--line); border-radius:7px; background:color-mix(in srgb,var(--panel),var(--bg) 28%); color:var(--text); font:inherit; }}
    textarea {{ min-height:160px; resize:vertical; padding:12px; line-height:1.45; }}
    input[type=file] {{ padding:8px; }}
    input[type=range] {{ accent-color:var(--accent); }}
    label {{ display:block; margin:0 0 6px; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:14px; margin:16px 0; }}
    .file-row {{ margin-top:14px; }}
    button {{ height:42px; border:1px solid var(--accent); border-radius:7px; background:var(--accent); color:white; font:inherit; font-weight:650; cursor:pointer; }}
    button:disabled {{ opacity:.7; cursor:wait; }}
    .links {{ display:flex; gap:10px; flex-wrap:wrap; justify-content:flex-end; }}
    a {{ color:var(--accent); text-decoration:none; }}
    .link-button, .download {{ border:1px solid var(--line); border-radius:7px; padding:8px 10px; background:var(--panel); color:var(--text); font-size:13px; }}
    .output {{ display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; margin-top:14px; padding-top:14px; border-top:1px solid var(--line); }}
    audio {{ width:100%; min-width:0; }}
    .download {{ display:none; white-space:nowrap; }}
    .status {{ min-height:22px; margin-top:10px; }}
    .status.error {{ color:var(--error); }}
    @media (max-width:760px) {{ header,.output {{ display:block; }} .links {{ justify-content:flex-start; margin-top:12px; }} .grid {{ grid-template-columns:1fr; }} main {{ width:calc(100vw - 20px); margin-top:16px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div><h1>Chatterbox TTS</h1><p class="subtitle">Local expressive speech and voice-cloning candidate</p></div>
      <nav class="links"><a class="link-button" href="/docs">API Docs</a><a class="link-button" href="/health">Health</a></nav>
    </header>
    <section class="surface">
      <label for="text">Text</label>
      <textarea id="text">Chatterbox is available as a local expressive text to speech backend.</textarea>
      <div class="file-row"><label for="prompt">Optional voice prompt WAV</label><input id="prompt" type="file" accept="audio/*"></div>
      <div class="grid">
        <div><label>Exaggeration <span id="exv">0.50</span></label><input id="exaggeration" type="range" min="0" max="2" step="0.05" value="0.5"></div>
        <div><label>CFG <span id="cfgv">0.50</span></label><input id="cfg" type="range" min="0" max="1" step="0.05" value="0.5"></div>
        <div><label>Temperature <span id="tempv">0.80</span></label><input id="temperature" type="range" min="0.05" max="2" step="0.05" value="0.8"></div>
        <button id="generate" type="button">Generate</button>
      </div>
      <div class="output"><audio id="audio" controls></audio><a id="download" class="download" download="chatterbox.wav">Download WAV</a></div>
      <div id="status" class="status" role="status"></div>
    </section>
  </main>
  <script>
    const modelId = {model_id};
    const ids = ["exaggeration", "cfg", "temperature"];
    const labels = {{exaggeration:"exv", cfg:"cfgv", temperature:"tempv"}};
    const text = document.getElementById("text"), prompt = document.getElementById("prompt");
    const audio = document.getElementById("audio"), download = document.getElementById("download");
    const generate = document.getElementById("generate"), status = document.getElementById("status");
    let currentObjectUrl = null;
    function setStatus(message, isError=false) {{ status.textContent = message; status.classList.toggle("error", isError); }}
    function syncLabels() {{ for (const id of ids) document.getElementById(labels[id]).textContent = Number(document.getElementById(id).value).toFixed(2); }}
    ids.forEach(id => document.getElementById(id).addEventListener("input", syncLabels));
    syncLabels(); setStatus("Ready.");
    generate.addEventListener("click", async () => {{
      if (!text.value.trim()) return setStatus("Enter text before generating audio.", true);
      generate.disabled = true; setStatus("Generating audio...");
      try {{
        const form = new FormData();
        form.append("model", modelId); form.append("input", text.value.trim()); form.append("response_format", "wav");
        form.append("exaggeration", document.getElementById("exaggeration").value);
        form.append("cfg_weight", document.getElementById("cfg").value);
        form.append("temperature", document.getElementById("temperature").value);
        if (prompt.files[0]) form.append("audio_prompt", prompt.files[0]);
        const response = await fetch("/v1/audio/speech-form", {{method:"POST", body:form}});
        if (!response.ok) throw new Error(await response.text());
        const blob = await response.blob();
        if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl);
        currentObjectUrl = URL.createObjectURL(blob); audio.src = currentObjectUrl; download.href = currentObjectUrl; download.style.display = "inline-flex";
        setStatus(`Generated ${{Math.round(blob.size / 1024)}} KB WAV.`);
      }} catch (error) {{ setStatus(error.message || String(error), true); }} finally {{ generate.disabled = false; }}
    }});
  </script>
</body>
</html>
"""


def _ensure_model() -> ChatterboxTTS:
    global model, model_load_error
    if model is not None:
        return model
    try:
        model = ChatterboxTTS.from_pretrained(DEVICE)
        model_load_error = None
        return model
    except Exception as exc:
        model_load_error = str(exc)
        raise HTTPException(status_code=503, detail=f"Chatterbox model failed to load: {model_load_error}") from exc


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse(_ui_html())


@app.head("/")
def ui_head() -> Response:
    return Response(status_code=200)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": model_load_error is None,
        "model": SERVICE_MODEL_ID,
        "device": DEVICE,
        "model_loaded": model is not None,
        "load_error": model_load_error,
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    return {"object": "list", "data": [{"id": SERVICE_MODEL_ID, "object": "model", "owned_by": "local-chatterbox"}]}


def _generate(
    text: str,
    response_format: str,
    audio_prompt_path: str | None,
    exaggeration: float,
    cfg_weight: float,
    temperature: float,
    top_p: float = 1.0,
) -> Response:
    loaded_model = _ensure_model()
    if not text.strip():
        raise HTTPException(status_code=400, detail="Input text is required")
    wav = loaded_model.generate(
        text.strip(),
        audio_prompt_path=audio_prompt_path,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
        temperature=temperature,
        top_p=top_p,
    )
    return _audio_response(wav.squeeze(0).detach().cpu().numpy(), loaded_model.sr, response_format)


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest) -> Response:
    if request.model != SERVICE_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {request.model}")
    return _generate(
        request.input,
        request.response_format,
        None,
        request.exaggeration,
        request.cfg_weight,
        request.temperature,
        request.top_p,
    )


@app.post("/v1/audio/speech-form")
async def speech_form(
    model_name: str = Form(default=SERVICE_MODEL_ID, alias="model"),
    input_text: str = Form(alias="input"),
    response_format: Literal["wav", "mp3", "flac", "pcm"] = Form(default="wav"),
    exaggeration: float = Form(default=0.5),
    cfg_weight: float = Form(default=0.5),
    temperature: float = Form(default=0.8),
    top_p: float = Form(default=1.0),
    audio_prompt: UploadFile | None = File(default=None),
) -> Response:
    if model_name != SERVICE_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model_name}")
    prompt_path = None
    if audio_prompt is not None and audio_prompt.filename:
        suffix = Path(audio_prompt.filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await audio_prompt.read())
            prompt_path = tmp.name
    try:
        return _generate(input_text, response_format, prompt_path, exaggeration, cfg_weight, temperature, top_p)
    finally:
        if prompt_path:
            Path(prompt_path).unlink(missing_ok=True)
