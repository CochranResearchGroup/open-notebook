#!/usr/bin/env python3
"""OpenAI-compatible Orpheus TTS server with a small browser UI."""

from __future__ import annotations

import io
import json
import os
import uuid
from collections.abc import Iterator
from typing import Literal

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


def _configure_hugging_face_token() -> None:
    token = os.environ.get("HUGGING_FACE_TOKEN")
    if token:
        os.environ.setdefault("HF_TOKEN", token)
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)


_configure_hugging_face_token()

SERVICE_MODEL_ID = os.environ.get("ORPHEUS_OPENAI_MODEL", "orpheus-3b")
ORPHEUS_MODEL_NAME = os.environ.get("ORPHEUS_MODEL_NAME", "canopylabs/orpheus-tts-0.1-finetune-prod")
ORPHEUS_DTYPE = os.environ.get("ORPHEUS_DTYPE", "bfloat16")
ORPHEUS_BACKEND = os.environ.get("ORPHEUS_BACKEND", "vllm").lower()
SAMPLE_RATE = int(os.environ.get("ORPHEUS_SAMPLE_RATE", "24000"))
AVAILABLE_VOICES = ["zoe", "zac", "jess", "leo", "mia", "julia", "leah"]
DEFAULT_VOICE = os.environ.get("ORPHEUS_DEFAULT_VOICE", "zoe")
OPENAI_VOICE_ALIASES = {
    "alloy": DEFAULT_VOICE,
    "ash": "zac",
    "ballad": "leo",
    "coral": "julia",
    "echo": "leo",
    "fable": "zac",
    "nova": "mia",
    "onyx": "leo",
    "sage": "leah",
    "shimmer": "zoe",
}

app = FastAPI(title="Orpheus OpenAI-compatible TTS")
model: object | None = None
model_load_error: str | None = None


class SpeechRequest(BaseModel):
    model: str = Field(default=SERVICE_MODEL_ID)
    input: str
    voice: str = Field(default=DEFAULT_VOICE)
    response_format: Literal["wav", "mp3", "flac", "pcm"] = "wav"
    temperature: float = Field(default=0.6, ge=0.05, le=2.0)
    top_p: float = Field(default=0.8, ge=0.05, le=1.0)
    max_tokens: int = Field(default=1200, ge=64, le=4096)
    repetition_penalty: float = Field(default=1.3, ge=0.5, le=2.5)


def _dtype() -> torch.dtype:
    return {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }.get(ORPHEUS_DTYPE, torch.bfloat16)


def _audio_response(audio_bytes: bytes, response_format: str) -> Response:
    if response_format == "pcm":
        return Response(content=audio_bytes, media_type="application/octet-stream")
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0
    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format=response_format.upper())
    media_type = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "flac": "audio/flac",
    }.get(response_format, "audio/wav")
    return Response(content=buffer.getvalue(), media_type=media_type)


class TransformersOrpheusModel:
    """Small Orpheus backend for hosts where vLLM is unavailable or unstable."""

    def __init__(self, model_name: str, dtype: torch.dtype):
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.model_name = model_name
        self.dtype = dtype
        self.device = os.environ.get("ORPHEUS_TRANSFORMERS_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, token=token)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            dtype=dtype,
            token=token,
            low_cpu_mem_usage=True,
        )
        self.model.to(self.device)
        self.model.eval()

    def _format_prompt(self, prompt: str, voice: str | None = None) -> str:
        if voice:
            prompt = f"{voice}: {prompt}"
        prompt_tokens = self.tokenizer(prompt, return_tensors="pt")
        start_token = torch.tensor([[128259]], dtype=torch.int64)
        end_tokens = torch.tensor([[128009, 128260, 128261, 128257]], dtype=torch.int64)
        all_input_ids = torch.cat([start_token, prompt_tokens.input_ids, end_tokens], dim=1)
        return self.tokenizer.decode(all_input_ids[0])

    def generate_tokens_sync(
        self,
        prompt: str,
        voice: str | None = None,
        request_id: str = "req-001",
        temperature: float = 0.6,
        top_p: float = 0.8,
        max_tokens: int = 1200,
        stop_token_ids: list[int] | None = None,
        repetition_penalty: float = 1.3,
    ) -> Iterator[str]:
        del request_id
        prompt_string = self._format_prompt(prompt, voice)
        inputs = self.tokenizer(prompt_string, return_tensors="pt").to(self.device)
        pad_token_id = self.tokenizer.pad_token_id or self.tokenizer.eos_token_id
        stop_token_ids = stop_token_ids or [49158]
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                do_sample=True,
                temperature=temperature,
                top_p=top_p,
                max_new_tokens=max_tokens,
                repetition_penalty=repetition_penalty,
                eos_token_id=stop_token_ids,
                pad_token_id=pad_token_id,
            )
        generated_ids = output_ids[0, inputs["input_ids"].shape[-1] :].tolist()
        for token_id in generated_ids:
            yield self.tokenizer.decode([token_id], skip_special_tokens=False)

    def generate_speech(self, **kwargs: object) -> Iterator[bytes]:
        from orpheus_tts.decoder import tokens_decoder_sync

        return tokens_decoder_sync(self.generate_tokens_sync(**kwargs))


def _ui_html() -> str:
    model_id = json.dumps(SERVICE_MODEL_ID)
    voices = json.dumps(AVAILABLE_VOICES)
    default_voice = json.dumps(DEFAULT_VOICE)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Orpheus TTS</title>
  <style>
    :root {{ color-scheme: light dark; --bg:#f7f7f4; --panel:#fff; --text:#202124; --muted:#62665f; --line:#d9ddd4; --accent:#7c3aed; --error:#b42318; }}
    @media (prefers-color-scheme: dark) {{ :root {{ --bg:#131217; --panel:#1e1b24; --text:#f4f2f7; --muted:#beb7c8; --line:#3a3442; --accent:#a78bfa; --error:#f97066; }} }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ width:min(980px, calc(100vw - 32px)); margin:32px auto; }}
    header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom:18px; }}
    h1 {{ margin:0 0 4px; font-size:28px; line-height:1.15; letter-spacing:0; }}
    .subtitle, label, .status {{ color:var(--muted); font-size:13px; }}
    .surface {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 14px 32px rgba(20,24,20,.10); }}
    textarea, select, input {{ width:100%; border:1px solid var(--line); border-radius:7px; background:color-mix(in srgb,var(--panel),var(--bg) 28%); color:var(--text); font:inherit; }}
    textarea {{ min-height:160px; resize:vertical; padding:12px; line-height:1.45; }}
    select {{ height:40px; padding:0 10px; }}
    input[type=range] {{ accent-color:var(--accent); }}
    label {{ display:block; margin:0 0 6px; }}
    .grid {{ display:grid; grid-template-columns:minmax(150px,1fr) repeat(3,minmax(120px,1fr)); gap:14px; margin:16px 0; }}
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
      <div><h1>Orpheus TTS</h1><p class="subtitle">Local LLM-style expressive speech backend</p></div>
      <nav class="links"><a class="link-button" href="/docs">API Docs</a><a class="link-button" href="/health">Health</a></nav>
    </header>
    <section class="surface">
      <label for="text">Text</label>
      <textarea id="text">Orpheus is available as a local expressive speech backend.</textarea>
      <div class="grid">
        <div><label for="voice">Voice</label><select id="voice"></select></div>
        <div><label>Temperature <span id="tempv">0.60</span></label><input id="temperature" type="range" min="0.05" max="2" step="0.05" value="0.6"></div>
        <div><label>Top P <span id="topv">0.80</span></label><input id="top_p" type="range" min="0.05" max="1" step="0.05" value="0.8"></div>
        <button id="generate" type="button">Generate</button>
      </div>
      <div class="output"><audio id="audio" controls></audio><a id="download" class="download" download="orpheus.wav">Download WAV</a></div>
      <div id="status" class="status" role="status"></div>
    </section>
  </main>
  <script>
    const modelId = {model_id}, voices = {voices}, defaultVoice = {default_voice};
    const voice = document.getElementById("voice"), text = document.getElementById("text");
    const temperature = document.getElementById("temperature"), topP = document.getElementById("top_p");
    const audio = document.getElementById("audio"), download = document.getElementById("download");
    const generate = document.getElementById("generate"), status = document.getElementById("status");
    let currentObjectUrl = null;
    for (const v of voices) {{ const opt = document.createElement("option"); opt.value = v; opt.textContent = v; opt.selected = v === defaultVoice; voice.appendChild(opt); }}
    function setStatus(message, isError=false) {{ status.textContent = message; status.classList.toggle("error", isError); }}
    function syncLabels() {{ document.getElementById("tempv").textContent = Number(temperature.value).toFixed(2); document.getElementById("topv").textContent = Number(topP.value).toFixed(2); }}
    temperature.addEventListener("input", syncLabels); topP.addEventListener("input", syncLabels); syncLabels(); setStatus("Ready.");
    generate.addEventListener("click", async () => {{
      if (!text.value.trim()) return setStatus("Enter text before generating audio.", true);
      generate.disabled = true; setStatus("Generating audio...");
      try {{
        const response = await fetch("/v1/audio/speech", {{
          method:"POST", headers:{{"Content-Type":"application/json"}},
          body:JSON.stringify({{model:modelId,input:text.value.trim(),voice:voice.value,response_format:"wav",temperature:Number(temperature.value),top_p:Number(topP.value)}})
        }});
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


def _ensure_model() -> object:
    global model, model_load_error
    if model is not None:
        return model
    try:
        if ORPHEUS_BACKEND == "transformers":
            model = TransformersOrpheusModel(model_name=ORPHEUS_MODEL_NAME, dtype=_dtype())
        elif ORPHEUS_BACKEND == "vllm":
            from orpheus_tts import OrpheusModel

            model = OrpheusModel(model_name=ORPHEUS_MODEL_NAME, dtype=_dtype())
        else:
            raise ValueError(f"Unsupported Orpheus backend: {ORPHEUS_BACKEND}")
        model_load_error = None
        return model
    except Exception as exc:
        model_load_error = str(exc)
        raise HTTPException(status_code=503, detail=f"Orpheus model failed to load: {model_load_error}") from exc


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
        "backend": ORPHEUS_BACKEND,
        "upstream_model": ORPHEUS_MODEL_NAME,
        "voices": AVAILABLE_VOICES,
        "model_loaded": model is not None,
        "load_error": model_load_error,
    }


@app.get("/v1/models")
def models() -> dict[str, object]:
    return {"object": "list", "data": [{"id": SERVICE_MODEL_ID, "object": "model", "owned_by": "local-orpheus"}]}


@app.get("/v1/audio/voices")
def voices() -> dict[str, object]:
    return {"voices": AVAILABLE_VOICES, "default": DEFAULT_VOICE}


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest) -> Response:
    loaded_model = _ensure_model()
    if request.model != SERVICE_MODEL_ID:
        raise HTTPException(status_code=404, detail=f"Unknown model: {request.model}")
    voice = OPENAI_VOICE_ALIASES.get(request.voice, request.voice) if request.voice else DEFAULT_VOICE
    if voice not in AVAILABLE_VOICES:
        raise HTTPException(status_code=400, detail=f"Unknown voice: {request.voice}")
    if not request.input.strip():
        raise HTTPException(status_code=400, detail="Input text is required")

    chunks = loaded_model.generate_speech(
        prompt=request.input.strip(),
        voice=voice,
        request_id=str(uuid.uuid4()),
        temperature=request.temperature,
        top_p=request.top_p,
        max_tokens=request.max_tokens,
        repetition_penalty=request.repetition_penalty,
    )
    audio_bytes = b"".join(chunks)
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="Orpheus produced no audio")
    return _audio_response(audio_bytes, request.response_format)
