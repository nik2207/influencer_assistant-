from __future__ import annotations

from ..config import settings

_model = None

WHISPER_HINT = {"en": "en", "hi": "hi", "mr": "mr"}


class SpeechError(Exception):
    """STT failure with a stable code for API mapping."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def whisper_language_hint(profile_lang: str | None) -> str | None:
    if not profile_lang:
        return None
    return WHISPER_HINT.get(profile_lang)


def transcribe(path: str, language: str | None = None) -> dict:
    """Speech to text using faster-whisper (install requirements-ml.txt)."""
    global _model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SpeechError(
            "unavailable",
            "Speech-to-text needs faster-whisper. Run: pip install -r requirements-ml.txt",
        ) from exc
    try:
        if _model is None:
            _model = WhisperModel(settings.whisper_model, compute_type="int8")
        hint = WHISPER_HINT.get(language) if language and len(language) <= 3 else language
        segments, info = _model.transcribe(path, language=hint, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": info.language or (hint or "")}
    except SpeechError:
        raise
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "cuda" in msg or "out of memory" in msg:
            raise SpeechError("provider_failed", "Speech engine is overloaded. Try again in a moment.") from exc
        raise SpeechError("provider_failed", "Speech-to-text failed. Please try again.") from exc
    except Exception as exc:  # PyAV / corrupt audio
        name = type(exc).__name__
        mod = type(exc).__module__ or ""
        if "InvalidData" in name or "FFmpeg" in name or "av.error" in mod:
            raise SpeechError(
                "invalid_audio",
                "That recording could not be read. Speak for at least 2 seconds and try again.",
            ) from exc
        raise SpeechError("provider_failed", "Speech-to-text failed. Please try again.") from exc
