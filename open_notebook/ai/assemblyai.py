import os
import time
from dataclasses import dataclass
from typing import Any, BinaryIO, Optional, Union

import httpx
from esperanto import AIFactory
from esperanto.common_types import Model
from esperanto.common_types.stt import TranscriptionResponse
from esperanto.providers.stt.base import SpeechToTextModel

ASSEMBLYAI_PROVIDER = "assemblyai"
ASSEMBLYAI_DEFAULT_MODEL = "universal-3-pro"
ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
ASSEMBLYAI_STREAMING_MODELS = {"universal-streaming"}
ASSEMBLYAI_FACTORY_TARGET = "open_notebook.ai.assemblyai:AssemblyAISpeechToTextModel"


def assemblyai_api_key() -> str | None:
    return os.getenv("ASSEMBLYAI_API_KEY") or os.getenv("ASSEMBLY_AI_API_KEY")


def register_assemblyai_provider() -> None:
    AIFactory._provider_modules.setdefault("speech_to_text", {})[
        ASSEMBLYAI_PROVIDER
    ] = ASSEMBLYAI_FACTORY_TARGET


@dataclass
class AssemblyAISpeechToTextModel(SpeechToTextModel):
    """AssemblyAI pre-recorded speech-to-text adapter.

    Esperanto does not currently ship an AssemblyAI STT provider, but
    content-core and Open Notebook can use any object that implements the
    SpeechToTextModel contract.
    """

    def __post_init__(self):
        super().__post_init__()
        self.api_key = self.api_key or assemblyai_api_key()
        if not self.api_key:
            raise ValueError("AssemblyAI API key not found")
        self.base_url = (self.base_url or ASSEMBLYAI_BASE_URL).rstrip("/")
        self.timeout = float(self._config.get("timeout") or self.timeout or 3600)
        self.poll_interval = float(self._config.get("poll_interval") or 3)
        self.client = httpx.Client(timeout=self.timeout)
        self.async_client = httpx.AsyncClient(timeout=self.timeout)

    @property
    def provider(self) -> str:
        return ASSEMBLYAI_PROVIDER

    def _get_default_model(self) -> str:
        return ASSEMBLYAI_DEFAULT_MODEL

    def _get_models(self) -> list[Model]:
        return [
            Model(id="universal-3-pro", owned_by="assemblyai"),
            Model(id="universal-3", owned_by="assemblyai"),
        ]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.api_key or ""}

    def _handle_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            message = response.json().get("error") or response.text
        except Exception:
            message = response.text
        raise RuntimeError(f"AssemblyAI API error: {message}")

    def _read_audio(self, audio_file: Union[str, BinaryIO]) -> bytes:
        if isinstance(audio_file, str):
            with open(audio_file, "rb") as handle:
                return handle.read()
        return audio_file.read()

    def _transcript_payload(
        self,
        upload_url: str,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        model_name = self.get_model_name()
        if model_name in ASSEMBLYAI_STREAMING_MODELS:
            raise ValueError(
                f"AssemblyAI model '{model_name}' is streaming-only and cannot be used "
                "for pre-recorded source transcription."
            )

        payload: dict[str, Any] = {"audio_url": upload_url, "speech_models": [model_name]}
        if language:
            payload["language_code"] = language
        if prompt:
            payload["prompt"] = prompt

        for key in (
            "language_detection",
            "speaker_labels",
            "keyterms_prompt",
            "speech_models",
            "disfluencies",
        ):
            if key in self._config:
                payload[key] = self._config[key]
        return payload

    def _build_response(self, data: dict[str, Any]) -> TranscriptionResponse:
        return TranscriptionResponse(
            text=data.get("text") or "",
            language=data.get("language_code"),
            duration=data.get("audio_duration"),
            model=self.get_model_name(),
            provider=self.provider,
            metadata={
                "id": data.get("id"),
                "status": data.get("status"),
                "confidence": data.get("confidence"),
                "audio_url": data.get("audio_url"),
            },
        )

    def _poll_transcript(self, transcript_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            response = self.client.get(
                f"{self.base_url}/transcript/{transcript_id}",
                headers=self._headers(),
            )
            self._handle_error(response)
            data = response.json()
            status = data.get("status")
            if status == "completed":
                return data
            if status == "error":
                raise RuntimeError(data.get("error") or "AssemblyAI transcription failed")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AssemblyAI transcription timed out after {self.timeout}s"
                )
            time.sleep(self.poll_interval)

    async def _apoll_transcript(self, transcript_id: str) -> dict[str, Any]:
        import asyncio

        deadline = time.monotonic() + self.timeout
        while True:
            response = await self.async_client.get(
                f"{self.base_url}/transcript/{transcript_id}",
                headers=self._headers(),
            )
            self._handle_error(response)
            data = response.json()
            status = data.get("status")
            if status == "completed":
                return data
            if status == "error":
                raise RuntimeError(data.get("error") or "AssemblyAI transcription failed")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AssemblyAI transcription timed out after {self.timeout}s"
                )
            await asyncio.sleep(self.poll_interval)

    def transcribe(
        self,
        audio_file: Union[str, BinaryIO],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> TranscriptionResponse:
        upload = self.client.post(
            f"{self.base_url}/upload",
            headers=self._headers(),
            content=self._read_audio(audio_file),
        )
        self._handle_error(upload)
        upload_url = upload.json()["upload_url"]

        transcript = self.client.post(
            f"{self.base_url}/transcript",
            headers=self._headers(),
            json=self._transcript_payload(upload_url, language=language, prompt=prompt),
        )
        self._handle_error(transcript)
        data = self._poll_transcript(transcript.json()["id"])
        return self._build_response(data)

    async def atranscribe(
        self,
        audio_file: Union[str, BinaryIO],
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> TranscriptionResponse:
        upload = await self.async_client.post(
            f"{self.base_url}/upload",
            headers=self._headers(),
            content=self._read_audio(audio_file),
        )
        self._handle_error(upload)
        upload_url = upload.json()["upload_url"]

        transcript = await self.async_client.post(
            f"{self.base_url}/transcript",
            headers=self._headers(),
            json=self._transcript_payload(upload_url, language=language, prompt=prompt),
        )
        self._handle_error(transcript)
        data = await self._apoll_transcript(transcript.json()["id"])
        return self._build_response(data)
