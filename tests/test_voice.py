"""Phase 14B — voice API, validation, language hints, and voice financial approvals."""
from io import BytesIO
from unittest.mock import patch

import pytest

from app.services import tools
from app.services.voice_audio import VoiceAudioError, validate_audio_upload
from tests.test_smoke import auth_headers, client, chat


def _voice_post(h, data=None, language=None):
    if data is None:
        data = b"0" * 128
    files = {"file": ("voice.webm", BytesIO(data), "audio/webm")}
    form = {"language": language} if language else {}
    return client.post("/voice/chat", headers=h, files=files, data=form)


def test_voice_missing_file_422():
    h = auth_headers("voice-missing@example.com")
    r = client.post("/voice/chat", headers=h)
    assert r.status_code == 422
    assert any("file" in str(x) for x in (r.json().get("detail") if isinstance(r.json().get("detail"), list) else []))


def test_voice_file_too_small_422():
    h = auth_headers("voice-small@example.com")
    r = _voice_post(h, b"tiny")
    assert r.status_code == 422
    assert "short" in r.json()["detail"].lower()


def test_voice_empty_transcript_422():
    h = auth_headers("voice-empty@example.com")
    with patch("app.routers.voice.speech.transcribe", return_value={"text": "", "language": "en"}):
        r = _voice_post(h)
    assert r.status_code == 422
    assert "could not hear" in r.json()["detail"].lower()


def test_voice_invalid_audio_422():
    h = auth_headers("voice-bad@example.com")
    from app.services.speech import SpeechError

    with patch("app.routers.voice.speech.transcribe", side_effect=SpeechError("invalid_audio", "bad audio")):
        r = _voice_post(h)
    assert r.status_code == 422
    assert "bad audio" in r.json()["detail"]


def test_voice_stt_unavailable_503():
    h = auth_headers("voice-503@example.com")
    from app.services.speech import SpeechError

    with patch("app.routers.voice.speech.transcribe", side_effect=SpeechError("unavailable", "no whisper")):
        r = _voice_post(h)
    assert r.status_code == 503


@patch("app.routers.voice.speech.transcribe")
def test_voice_chat_success_shape(mock_stt):
    h = auth_headers("voice-ok@example.com")
    mock_stt.return_value = {"text": "hello assistant", "language": "en"}
    r = _voice_post(h, language="hi")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "hello assistant"
    assert body["detected_language"] == "en"
    assert body["language_hint"] == "hi"
    assert "reply" in body
    mock_stt.assert_called_once()
    args = mock_stt.call_args[0]
    assert args[1] == "hi"


@patch("app.routers.voice.speech.transcribe")
def test_voice_history_marks_source(mock_stt):
    h = auth_headers("voice-hist@example.com")
    mock_stt.return_value = {"text": "List my deals", "language": "en"}
    assert _voice_post(h).status_code == 200
    hist = client.get("/agent/history", headers=h).json()
    user_lines = [m for m in hist if m["role"] == "user"]
    assert user_lines and user_lines[-1]["source"] == "voice"
    assert user_lines[-1]["content"] == "List my deals"


@patch("app.routers.voice.speech.transcribe")
def test_voice_invoice_requires_approval(mock_stt):
    h = auth_headers("voice-inv@example.com")
    deal = client.post("/deals", json={"brand": "Nykaa", "value_inr": 5000}, headers=h).json()
    deal_id = deal["id"]
    mock_stt.return_value = {"text": f"create invoice for deal {deal_id}", "language": "en"}
    out = _voice_post(h).json()
    assert out["pending"], out
    assert out["pending"][0]["tool"] == "create_invoice"
    assert out["pending"][0]["recognized_text"]
    assert str(deal_id) in out["pending"][0]["summary"] or "deal" in out["pending"][0]["summary"].lower()
    listed = client.get("/invoices", headers=h).json()
    assert listed == []


def test_text_invoice_still_direct_without_pending():
    h = auth_headers("text-inv@example.com")
    deal_id = client.post("/deals", json={"brand": "Boat", "value_inr": 8000}, headers=h).json()["id"]
    out = chat(h, f"create invoice for deal {deal_id}")
    assert out["pending"] == []
    invs = client.get("/invoices", headers=h).json()
    assert len(invs) >= 1


def test_validate_audio_upload_ok():
    assert validate_audio_upload(b"x" * 100, "voice.webm", "audio/webm") == ".webm"


def test_validate_audio_rejects_bad_mime():
    with pytest.raises(VoiceAudioError) as exc:
        validate_audio_upload(b"x" * 100, "x.txt", "text/plain")
    assert exc.value.code == "bad_type"


def test_needs_approval_voice_financial():
    assert tools.needs_approval("book_ride") is True
    assert tools.needs_approval("create_invoice", voice=True) is True
    assert tools.needs_approval("create_invoice", voice=False) is False
    assert tools.needs_approval("list_deals", voice=True) is False


def test_approval_summary_includes_recognized():
    s = tools.approval_summary("add_expense", {"amount_inr": 500, "description": "props"}, recognized="Add expense 500")
    assert "voice" in s.lower()
    assert "500" in s
