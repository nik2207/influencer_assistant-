"""Audio upload checks for voice endpoints (size, type, minimum payload)."""
from __future__ import annotations

import os

MAX_BYTES = 10 * 1024 * 1024
MIN_BYTES = 64

ALLOWED_SUFFIXES = frozenset({
    ".webm", ".ogg", ".opus", ".wav", ".mp3", ".m4a", ".mp4", ".mpeg", ".mpga",
})
ALLOWED_MIME_PREFIXES = (
    "audio/",
    "video/webm",  # browser MediaRecorder may send webm as video/*
)
ALLOWED_MIME_EXACT = frozenset({"application/ogg", "application/octet-stream"})


class VoiceAudioError(Exception):
    """User-facing validation failure (maps to HTTP 422)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _suffix_ok(filename: str | None) -> bool:
    ext = (os.path.splitext(filename or "")[1] or ".webm").lower()
    return ext in ALLOWED_SUFFIXES


def _mime_ok(content_type: str | None) -> bool:
    if not content_type:
        return True
    ct = content_type.split(";")[0].strip().lower()
    if ct in ALLOWED_MIME_EXACT:
        return True
    return any(ct.startswith(p) for p in ALLOWED_MIME_PREFIXES)


def validate_audio_upload(data: bytes, filename: str | None, content_type: str | None) -> str:
    """Return normalized file suffix for temp storage."""
    if len(data) > MAX_BYTES:
        raise VoiceAudioError("too_large", "Audio file too large (10 MB max).")
    if len(data) < MIN_BYTES:
        raise VoiceAudioError("too_short", "Recording too short. Hold the mic and speak for at least 2 seconds.")
    if not _mime_ok(content_type):
        raise VoiceAudioError("bad_type", "Unsupported audio type. Use the in-app mic or upload WebM, OGG or WAV.")
    if filename and not _suffix_ok(filename):
        raise VoiceAudioError("bad_type", "Unsupported audio file extension.")
    ext = os.path.splitext(filename or "")[1]
    return ext.lower() if ext else ".webm"
