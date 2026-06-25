from fastapi.testclient import TestClient


class FakeTranscription:
    text = "Sample transcript"
    language = "en"
    duration = 1.25
    model = "fake-stt"
    provider = "fake"


class FakeSpeechToText:
    def __init__(self):
        self.calls = []

    async def atranscribe(self, audio_file, language=None, prompt=None):
        self.calls.append(
            {
                "audio_file": audio_file,
                "language": language,
                "prompt": prompt,
            }
        )
        return FakeTranscription()


def test_audio_transcriptions_uses_default_stt(monkeypatch):
    from api.main import app
    from api.routers import audio

    fake_stt = FakeSpeechToText()

    async def fake_get_speech_to_text():
        return fake_stt

    monkeypatch.setattr(
        audio.model_manager,
        "get_speech_to_text",
        fake_get_speech_to_text,
    )

    client = TestClient(app)
    response = client.post(
        "/api/audio/transcriptions",
        data={"language": "en", "prompt": "names: Dia"},
        files={"file": ("sample.wav", b"fake audio", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "text": "Sample transcript",
        "language": "en",
        "duration": 1.25,
        "model": "fake-stt",
        "provider": "fake",
    }
    assert fake_stt.calls
    assert fake_stt.calls[0]["language"] == "en"
    assert fake_stt.calls[0]["prompt"] == "names: Dia"


def test_audio_transcriptions_requires_default_stt(monkeypatch):
    from api.main import app
    from api.routers import audio

    async def fake_get_speech_to_text():
        return None

    monkeypatch.setattr(
        audio.model_manager,
        "get_speech_to_text",
        fake_get_speech_to_text,
    )

    client = TestClient(app)
    response = client.post(
        "/api/audio/transcriptions",
        files={"file": ("sample.wav", b"fake audio", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "No default speech-to-text model configured"
