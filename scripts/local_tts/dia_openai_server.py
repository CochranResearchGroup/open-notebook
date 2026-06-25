#!/usr/bin/env python3
"""OpenAI-compatible Dia TTS server with a small browser UI."""

from __future__ import annotations

import io
import json
import os
import random
import tempfile
import uuid
from base64 import b64encode
from pathlib import Path
from typing import Literal

import httpx
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

SERVICE_MODEL_ID = os.environ.get("DIA_OPENAI_MODEL", "dia-1.6b")
DIA_MODEL_NAME = os.environ.get("DIA_MODEL_NAME", "nari-labs/Dia-1.6B-0626")
DIA_DEVICE = os.environ.get("DIA_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
DIA_COMPUTE_DTYPE = os.environ.get(
    "DIA_COMPUTE_DTYPE",
    "float16" if DIA_DEVICE == "cuda" else "float32",
)
SAMPLE_RATE = int(os.environ.get("DIA_SAMPLE_RATE", "44100"))
DEFAULT_VOICE = os.environ.get("DIA_DEFAULT_VOICE", "dialogue")
DEFAULT_MAX_TOKENS = int(os.environ.get("DIA_MAX_TOKENS", "860"))
DEFAULT_CFG_SCALE = float(os.environ.get("DIA_CFG_SCALE", "3.0"))
DEFAULT_TEMPERATURE = float(os.environ.get("DIA_TEMPERATURE", "1.3"))
DEFAULT_TOP_P = float(os.environ.get("DIA_TOP_P", "0.95"))
DEFAULT_CFG_FILTER_TOP_K = int(os.environ.get("DIA_CFG_FILTER_TOP_K", "45"))
DIA_TRANSCRIPTION_URL = os.environ.get("DIA_TRANSCRIPTION_URL", "").strip()
DIA_TRANSCRIPTION_AUTH_BEARER = (
    os.environ.get("DIA_TRANSCRIPTION_AUTH_BEARER")
    or os.environ.get("OPEN_NOTEBOOK_PASSWORD")
    or ""
).strip()
DIA_TRANSCRIPTION_TIMEOUT = float(os.environ.get("DIA_TRANSCRIPTION_TIMEOUT", "600"))

VOICE_ALIASES = {
    "alloy": "s1",
    "dialogue": "s1",
    "default": "s1",
    "coral": "s1",
    "nova": "s1",
    "shimmer": "s1",
    "ash": "s2",
    "echo": "s2",
    "fable": "s2",
    "onyx": "s2",
    "sage": "s2",
    "s1": "s1",
    "s2": "s2",
}
AVAILABLE_VOICES = sorted(VOICE_ALIASES)

app = FastAPI(title="Dia OpenAI-compatible TTS")
model: object | None = None
model_load_error: str | None = None


class SpeechRequest(BaseModel):
    model: str = Field(default=SERVICE_MODEL_ID)
    input: str
    voice: str = Field(default=DEFAULT_VOICE)
    response_format: Literal["wav", "mp3", "flac", "pcm"] = "wav"
    speed: float = Field(default=1.0, ge=0.1, le=5.0)
    max_tokens: int = Field(default=DEFAULT_MAX_TOKENS, ge=128, le=3072)
    cfg_scale: float = Field(default=DEFAULT_CFG_SCALE, ge=1.0, le=5.0)
    temperature: float = Field(default=DEFAULT_TEMPERATURE, ge=0.1, le=2.5)
    top_p: float = Field(default=DEFAULT_TOP_P, ge=0.05, le=1.0)
    cfg_filter_top_k: int = Field(default=DEFAULT_CFG_FILTER_TOP_K, ge=1, le=100)
    seed: int | None = Field(default=None)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


def _ensure_model() -> object:
    global model, model_load_error
    if model is not None:
        return model
    try:
        from dia.model import Dia

        model = Dia.from_pretrained(
            DIA_MODEL_NAME,
            compute_dtype=DIA_COMPUTE_DTYPE,
            device=torch.device(DIA_DEVICE),
        )
        model_load_error = None
        return model
    except Exception as exc:
        model_load_error = str(exc)
        raise HTTPException(status_code=503, detail=f"Dia model failed to load: {model_load_error}") from exc


def _format_prompt(text: str, voice: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Input text is required")
    if "[S1]" in stripped or "[S2]" in stripped:
        return stripped
    speaker = VOICE_ALIASES.get(voice, VOICE_ALIASES.get(DEFAULT_VOICE, "s1"))
    marker = "[S2]" if speaker == "s2" else "[S1]"
    return f"{marker} {stripped}"


def _combine_audio_prompt_text(audio_prompt_transcript: str | None, text: str, voice: str) -> str:
    prompt = _format_prompt(text, voice)
    transcript = (audio_prompt_transcript or "").strip()
    if not transcript:
        return prompt
    if "[S1]" not in transcript and "[S2]" not in transcript:
        transcript = f"[S1] {transcript}"
    return f"{transcript}\n{prompt}"


def _audio_response(audio: np.ndarray, response_format: str) -> Response:
    audio = np.asarray(audio).squeeze()
    buffer = io.BytesIO()
    if response_format == "pcm":
        buffer.write(audio.astype("float32").tobytes())
        return Response(content=buffer.getvalue(), media_type="application/octet-stream")
    sf.write(buffer, audio.astype(np.float32), SAMPLE_RATE, format=response_format.upper())
    media_type = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "flac": "audio/flac",
    }.get(response_format, "audio/wav")
    return Response(content=buffer.getvalue(), media_type=media_type)


def _apply_speed(audio: np.ndarray, speed: float) -> np.ndarray:
    audio = np.asarray(audio).squeeze()
    speed = max(0.1, min(speed, 5.0))
    if speed == 1.0 or audio.size == 0:
        return audio
    target_len = max(1, int(audio.shape[0] / speed))
    x_original = np.arange(audio.shape[0])
    x_resampled = np.linspace(0, audio.shape[0] - 1, target_len)
    return np.interp(x_resampled, x_original, audio).astype(np.float32)


def _transcription_headers() -> dict[str, str]:
    if not DIA_TRANSCRIPTION_AUTH_BEARER:
        return {}
    return {"Authorization": f"Bearer {DIA_TRANSCRIPTION_AUTH_BEARER}"}


async def _transcribe_audio_file(
    audio_file: UploadFile,
    *,
    language: str | None = None,
    prompt: str | None = None,
) -> dict[str, object]:
    if not DIA_TRANSCRIPTION_URL:
        raise HTTPException(
            status_code=422,
            detail="DIA_TRANSCRIPTION_URL is not configured for automatic sample transcription",
        )

    content = await audio_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Audio prompt file is empty")

    filename = audio_file.filename or "audio-prompt.wav"
    content_type = audio_file.content_type or "application/octet-stream"
    data: dict[str, str] = {}
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt

    try:
        async with httpx.AsyncClient(timeout=DIA_TRANSCRIPTION_TIMEOUT) as client:
            response = await client.post(
                DIA_TRANSCRIPTION_URL,
                headers=_transcription_headers(),
                files={"file": (filename, content, content_type)},
                data=data,
            )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Configured transcription service failed: {detail}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Configured transcription service failed: {exc}") from exc

    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="Configured transcription service returned no text")
    payload["text"] = text
    return payload


async def _write_upload_to_temp(audio_file: UploadFile) -> str:
    suffix = Path(audio_file.filename or "").suffix or ".wav"
    content = await audio_file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Audio prompt file is empty")
    temp_audio = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        temp_audio.write(content)
        temp_audio.flush()
        return temp_audio.name
    finally:
        temp_audio.close()


def _ui_html() -> str:
    model_id = json.dumps(SERVICE_MODEL_ID)
    voices = json.dumps(AVAILABLE_VOICES)
    default_voice = json.dumps(DEFAULT_VOICE)
    transcription_enabled = json.dumps(bool(DIA_TRANSCRIPTION_URL))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dia TTS</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f7f7f4; --panel:#fff; --text:#202124; --muted:#62665f; --line:#d9ddd4; --accent:#0d9488; --error:#b42318; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#101312; --panel:#1a1f1d; --text:#f2f6f4; --muted:#b8c1bd; --line:#333b37; --accent:#5eead4; --error:#f97066; }} }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ width:min(980px, calc(100vw - 32px)); margin:32px auto; }}
    header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:18px; }}
    h1 {{ margin:0 0 4px; font-size:28px; line-height:1.15; letter-spacing:0; }}
    .subtitle, label, .status {{ color:var(--muted); font-size:13px; }}
    .surface {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 14px 32px rgba(20,24,20,.10); }}
    textarea, select, input {{ width:100%; border:1px solid var(--line); border-radius:7px; background:color-mix(in srgb,var(--panel),var(--bg) 28%); color:var(--text); font:inherit; }}
    textarea {{ min-height:160px; resize:vertical; padding:12px; line-height:1.45; }}
    #sampleTranscript {{ min-height:78px; }}
    select {{ height:40px; padding:0 10px; }}
    input[type=file] {{ padding:9px; }}
    input[type=range] {{ accent-color:var(--accent); }}
    label {{ display:block; margin:0 0 6px; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:14px; margin:16px 0; }}
    .sample-grid {{ display:grid; grid-template-columns:minmax(220px,1fr) minmax(220px,1fr) auto; gap:14px; align-items:end; margin:16px 0; }}
    button {{ height:42px; border:1px solid var(--accent); border-radius:7px; background:var(--accent); color:white; font:inherit; font-weight:650; cursor:pointer; }}
    button.secondary {{ background:transparent; color:var(--text); border-color:var(--line); }}
    button:disabled {{ opacity:.7; cursor:wait; }}
    .links {{ display:flex; gap:10px; flex-wrap:wrap; justify-content:flex-end; }}
    a {{ color:var(--accent); text-decoration:none; }}
    .link-button, .download {{ border:1px solid var(--line); border-radius:7px; padding:8px 10px; background:var(--panel); color:var(--text); font-size:13px; }}
    .output {{ display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; margin-top:14px; padding-top:14px; border-top:1px solid var(--line); }}
    audio {{ width:100%; min-width:0; }}
    .download {{ display:none; white-space:nowrap; }}
    .status {{ min-height:22px; margin-top:10px; }}
    .status.error {{ color:var(--error); }}
    @media (max-width:760px) {{ header,.output {{ display:block; }} .links {{ justify-content:flex-start; margin-top:12px; }} .grid,.sample-grid {{ grid-template-columns:1fr; }} main {{ width:calc(100vw - 20px); margin-top:16px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div><h1>Dia TTS</h1><p class="subtitle">Local dialogue-oriented speech backend</p></div>
      <nav class="links"><a class="link-button" href="/docs">API Docs</a><a class="link-button" href="/health">Health</a></nav>
    </header>
    <section class="surface">
      <label for="text">Text</label>
      <textarea id="text">[S1] Dia is available as a local OpenAI-compatible speech backend.</textarea>
      <div class="sample-grid">
        <div><label for="sample">Voice Sample</label><input id="sample" type="file" accept="audio/*"></div>
        <div><label for="sampleTranscript">Sample Transcript</label><textarea id="sampleTranscript" placeholder="Optional. Leave blank to use the configured speech-to-text model."></textarea></div>
        <button id="transcribe" class="secondary" type="button">Transcribe Sample</button>
      </div>
      <div class="grid">
        <div><label for="voice">Voice Alias</label><select id="voice"></select></div>
        <div><label>Temperature <span id="tempv">1.30</span></label><input id="temperature" type="range" min="0.1" max="2.5" step="0.05" value="1.3"></div>
        <div><label>CFG <span id="cfgv">3.00</span></label><input id="cfg" type="range" min="1" max="5" step="0.1" value="3"></div>
        <button id="generate" type="button">Generate</button>
      </div>
      <div class="output"><audio id="audio" controls></audio><a id="download" class="download" download="dia.wav">Download WAV</a></div>
      <div id="status" class="status" role="status"></div>
    </section>
  </main>
  <script>
    const modelId = {model_id}, voices = {voices}, defaultVoice = {default_voice}, transcriptionEnabled = {transcription_enabled};
    const voice = document.getElementById("voice"), text = document.getElementById("text");
    const sample = document.getElementById("sample"), sampleTranscript = document.getElementById("sampleTranscript");
    const temperature = document.getElementById("temperature"), cfg = document.getElementById("cfg");
    const audio = document.getElementById("audio"), download = document.getElementById("download");
    const generate = document.getElementById("generate"), transcribe = document.getElementById("transcribe"), status = document.getElementById("status");
    let currentObjectUrl = null;
    for (const v of voices) {{ const opt = document.createElement("option"); opt.value = v; opt.textContent = v; opt.selected = v === defaultVoice; voice.appendChild(opt); }}
    function setStatus(message, isError=false) {{ status.textContent = message; status.classList.toggle("error", isError); }}
    function syncLabels() {{ document.getElementById("tempv").textContent = Number(temperature.value).toFixed(2); document.getElementById("cfgv").textContent = Number(cfg.value).toFixed(2); }}
    temperature.addEventListener("input", syncLabels); cfg.addEventListener("input", syncLabels); syncLabels(); setStatus("Ready.");
    transcribe.disabled = !transcriptionEnabled;
    transcribe.title = transcriptionEnabled ? "Transcribe the uploaded sample" : "Configure DIA_TRANSCRIPTION_URL to enable automatic transcription";
    transcribe.addEventListener("click", async () => {{
      if (!sample.files.length) return setStatus("Choose a voice sample first.", true);
      transcribe.disabled = true; setStatus("Transcribing sample...");
      try {{
        const form = new FormData(); form.append("file", sample.files[0]);
        const response = await fetch("/v1/audio/transcriptions", {{ method:"POST", body:form }});
        if (!response.ok) throw new Error(await response.text());
        const payload = await response.json();
        sampleTranscript.value = payload.text || "";
        setStatus(`Transcribed sample${{payload.model ? " with " + payload.model : ""}}.`);
      }} catch (error) {{ setStatus(error.message || String(error), true); }} finally {{ transcribe.disabled = !transcriptionEnabled; }}
    }});
    generate.addEventListener("click", async () => {{
      if (!text.value.trim()) return setStatus("Enter text before generating audio.", true);
      generate.disabled = true; setStatus("Generating audio...");
      try {{
        let response;
        if (sample.files.length) {{
          const form = new FormData();
          form.append("model", modelId); form.append("input", text.value.trim()); form.append("voice", voice.value);
          form.append("response_format", "wav"); form.append("temperature", temperature.value); form.append("cfg_scale", cfg.value);
          form.append("auto_transcribe", "true"); form.append("audio_prompt", sample.files[0]);
          if (sampleTranscript.value.trim()) form.append("audio_prompt_transcript", sampleTranscript.value.trim());
          response = await fetch("/v1/audio/speech-form", {{ method:"POST", body:form }});
        }} else {{
          response = await fetch("/v1/audio/speech", {{
            method:"POST", headers:{{"Content-Type":"application/json"}},
            body:JSON.stringify({{model:modelId,input:text.value.trim(),voice:voice.value,response_format:"wav",temperature:Number(temperature.value),cfg_scale:Number(cfg.value)}})
          }});
        }}
        if (!response.ok) throw new Error(await response.text());
        const transcript = response.headers.get("X-Dia-Audio-Prompt-Transcript-B64");
        if (transcript && !sampleTranscript.value.trim()) sampleTranscript.value = new TextDecoder().decode(Uint8Array.from(atob(transcript), c => c.charCodeAt(0)));
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
        "upstream_model": DIA_MODEL_NAME,
        "device": DIA_DEVICE,
        "compute_dtype": DIA_COMPUTE_DTYPE,
        "sample_rate": SAMPLE_RATE,
        "model_loaded": model is not None,
        "load_error": model_load_error,
        "defaults": {
            "max_tokens": DEFAULT_MAX_TOKENS,
            "cfg_scale": DEFAULT_CFG_SCALE,
            "temperature": DEFAULT_TEMPERATURE,
            "top_p": DEFAULT_TOP_P,
            "cfg_filter_top_k": DEFAULT_CFG_FILTER_TOP_K,
        },
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    return {"object": "list", "data": [{"id": SERVICE_MODEL_ID, "object": "model", "owned_by": "local-dia"}]}


@app.get("/v1/audio/voices")
def voices() -> dict[str, object]:
    return {"voices": AVAILABLE_VOICES, "default": DEFAULT_VOICE}


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
) -> JSONResponse:
    payload = await _transcribe_audio_file(file, language=language, prompt=prompt)
    return JSONResponse(payload)


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest) -> Response:
    loaded_model = _ensure_model()
    if request.model != SERVICE_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {request.model}")
    if request.voice and request.voice not in VOICE_ALIASES:
        raise HTTPException(status_code=400, detail=f"Unknown voice alias: {request.voice}")
    if request.seed is not None:
        _set_seed(request.seed)

    prompt = _format_prompt(request.input, request.voice or DEFAULT_VOICE)
    try:
        with torch.inference_mode():
            audio = loaded_model.generate(
                prompt,
                max_tokens=request.max_tokens,
                cfg_scale=request.cfg_scale,
                temperature=request.temperature,
                top_p=request.top_p,
                cfg_filter_top_k=request.cfg_filter_top_k,
                use_torch_compile=False,
                verbose=False,
            )
    except Exception as exc:
        request_id = str(uuid.uuid4())
        raise HTTPException(status_code=500, detail=f"Dia generation failed ({request_id}): {exc}") from exc

    if audio is None or len(audio) == 0:
        raise HTTPException(status_code=500, detail="Dia produced no audio")
    return _audio_response(_apply_speed(audio, request.speed), request.response_format)


@app.post("/v1/audio/speech-form")
async def speech_form(
    model: str = Form(default=SERVICE_MODEL_ID),
    input: str = Form(...),
    voice: str = Form(default=DEFAULT_VOICE),
    response_format: Literal["wav", "mp3", "flac", "pcm"] = Form(default="wav"),
    speed: float = Form(default=1.0),
    max_tokens: int = Form(default=DEFAULT_MAX_TOKENS),
    cfg_scale: float = Form(default=DEFAULT_CFG_SCALE),
    temperature: float = Form(default=DEFAULT_TEMPERATURE),
    top_p: float = Form(default=DEFAULT_TOP_P),
    cfg_filter_top_k: int = Form(default=DEFAULT_CFG_FILTER_TOP_K),
    seed: int | None = Form(default=None),
    audio_prompt: UploadFile | None = File(default=None),
    audio_prompt_transcript: str | None = Form(default=None),
    auto_transcribe: bool = Form(default=True),
    transcription_language: str | None = Form(default=None),
    transcription_prompt: str | None = Form(default=None),
) -> Response:
    loaded_model = _ensure_model()
    if model != SERVICE_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model}")
    if voice and voice not in VOICE_ALIASES:
        raise HTTPException(status_code=400, detail=f"Unknown voice alias: {voice}")
    if seed is not None:
        _set_seed(seed)

    temp_audio_path: str | None = None
    transcript = (audio_prompt_transcript or "").strip()
    if audio_prompt is not None:
        if not transcript and auto_transcribe:
            transcript_payload = await _transcribe_audio_file(
                audio_prompt,
                language=transcription_language,
                prompt=transcription_prompt,
            )
            transcript = str(transcript_payload.get("text") or "").strip()
        await audio_prompt.seek(0)
        temp_audio_path = await _write_upload_to_temp(audio_prompt)

    prompt = _combine_audio_prompt_text(transcript, input, voice or DEFAULT_VOICE)
    try:
        with torch.inference_mode():
            audio = loaded_model.generate(
                prompt,
                max_tokens=max(128, min(max_tokens, 3072)),
                cfg_scale=max(1.0, min(cfg_scale, 5.0)),
                temperature=max(0.1, min(temperature, 2.5)),
                top_p=max(0.05, min(top_p, 1.0)),
                cfg_filter_top_k=max(1, min(cfg_filter_top_k, 100)),
                use_torch_compile=False,
                audio_prompt=temp_audio_path,
                verbose=False,
            )
    except Exception as exc:
        request_id = str(uuid.uuid4())
        raise HTTPException(status_code=500, detail=f"Dia generation failed ({request_id}): {exc}") from exc
    finally:
        if temp_audio_path:
            try:
                Path(temp_audio_path).unlink(missing_ok=True)
            except Exception:
                pass

    if audio is None or len(audio) == 0:
        raise HTTPException(status_code=500, detail="Dia produced no audio")

    response = _audio_response(_apply_speed(audio, speed), response_format)
    if transcript:
        response.headers["X-Dia-Audio-Prompt-Transcript-B64"] = b64encode(
            transcript.encode("utf-8")
        ).decode("ascii")
    return response
