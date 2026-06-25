import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from open_notebook.ai.models import model_manager

router = APIRouter()


class AudioTranscriptionResponse(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    model: Optional[str] = None
    provider: Optional[str] = None


@router.post("/audio/transcriptions", response_model=AudioTranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
):
    """Transcribe an uploaded audio sample with the configured default STT model."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required")

    stt_model = await model_manager.get_speech_to_text()
    if stt_model is None:
        raise HTTPException(status_code=422, detail="No default speech-to-text model configured")

    suffix = Path(file.filename).suffix or ".wav"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp_audio:
            while chunk := await file.read(1024 * 1024):
                temp_audio.write(chunk)
            temp_audio.flush()

            result = await stt_model.atranscribe(
                audio_file=temp_audio.name,
                language=language,
                prompt=prompt,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Audio transcription failed: {exc}") from exc

    return AudioTranscriptionResponse(
        text=str(getattr(result, "text", "") or ""),
        language=getattr(result, "language", None),
        duration=getattr(result, "duration", None),
        model=getattr(result, "model", None),
        provider=getattr(result, "provider", None),
    )
