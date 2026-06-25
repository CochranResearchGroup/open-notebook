import os
from unittest.mock import AsyncMock, patch

import pytest
from esperanto import AIFactory

from open_notebook.ai.assemblyai import AssemblyAISpeechToTextModel
from open_notebook.ai.key_provider import get_api_key, provision_provider_keys
from open_notebook.domain.credential import Credential


class FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = str(data)

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/upload"):
            return FakeResponse({"upload_url": "https://cdn.example/audio.mp3"})
        if url.endswith("/transcript"):
            return FakeResponse({"id": "transcript-1", "status": "queued"})
        raise AssertionError(f"Unexpected POST {url}")

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return FakeResponse(
            {
                "id": "transcript-1",
                "status": "completed",
                "text": "hello from assemblyai",
                "language_code": "en",
                "audio_duration": 1.25,
                "confidence": 0.97,
                "audio_url": "https://cdn.example/audio.mp3",
            }
        )


class FakeAsyncClient(FakeClient):
    async def post(self, url, **kwargs):
        return super().post(url, **kwargs)

    async def get(self, url, **kwargs):
        return super().get(url, **kwargs)


def test_assemblyai_registers_with_esperanto_factory(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")
    with (
        patch("open_notebook.ai.assemblyai.httpx.Client", FakeClient),
        patch("open_notebook.ai.assemblyai.httpx.AsyncClient", FakeAsyncClient),
    ):
        model = AIFactory.create_speech_to_text(
            "assemblyai",
            "universal-3-pro",
            {"timeout": 5},
        )

    assert isinstance(model, AssemblyAISpeechToTextModel)
    assert model.provider == "assemblyai"


def test_assemblyai_transcribe_uses_upload_transcript_poll_flow(tmp_path, monkeypatch):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"audio-bytes")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")
    client = FakeClient()

    with (
        patch("open_notebook.ai.assemblyai.httpx.Client", return_value=client),
        patch("open_notebook.ai.assemblyai.httpx.AsyncClient", FakeAsyncClient),
    ):
        model = AssemblyAISpeechToTextModel(
            model_name="universal-3-pro",
            config={"timeout": 5, "poll_interval": 0},
        )
        result = model.transcribe(str(audio), language="en", prompt="names: Open Notebook")

    assert result.text == "hello from assemblyai"
    assert result.provider == "assemblyai"
    assert result.model == "universal-3-pro"
    upload_url, upload_kwargs = client.posts[0]
    assert upload_url.endswith("/upload")
    assert upload_kwargs["content"] == b"audio-bytes"
    transcript_url, transcript_kwargs = client.posts[1]
    assert transcript_url.endswith("/transcript")
    assert transcript_kwargs["json"]["audio_url"] == "https://cdn.example/audio.mp3"
    assert transcript_kwargs["json"]["speech_models"] == ["universal-3-pro"]
    assert transcript_kwargs["json"]["language_code"] == "en"
    assert transcript_kwargs["json"]["prompt"] == "names: Open Notebook"


def test_assemblyai_streaming_model_rejected_for_prerecorded(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")
    with (
        patch("open_notebook.ai.assemblyai.httpx.Client", FakeClient),
        patch("open_notebook.ai.assemblyai.httpx.AsyncClient", FakeAsyncClient),
    ):
        model = AssemblyAISpeechToTextModel(model_name="universal-streaming")

    with pytest.raises(ValueError, match="streaming-only"):
        model._transcript_payload("https://cdn.example/audio.mp3")


@pytest.mark.asyncio
async def test_assemblyai_key_provider_supports_alias(monkeypatch):
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    monkeypatch.setenv("ASSEMBLY_AI_API_KEY", "alias-key")

    assert await get_api_key("assemblyai") == "alias-key"


@pytest.mark.asyncio
async def test_assemblyai_key_provider_sets_primary_and_alias_from_credential(monkeypatch):
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)
    monkeypatch.delenv("ASSEMBLY_AI_API_KEY", raising=False)
    credential = Credential(
        name="AssemblyAI",
        provider="assemblyai",
        api_key="db-key",
    )

    with patch.object(
        Credential,
        "get_by_provider",
        new_callable=AsyncMock,
        return_value=[credential],
    ):
        assert await provision_provider_keys("assemblyai") is True

    assert os.getenv("ASSEMBLYAI_API_KEY") == "db-key"
    assert os.getenv("ASSEMBLY_AI_API_KEY") == "db-key"
