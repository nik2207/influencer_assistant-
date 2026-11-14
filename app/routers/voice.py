import os
import re
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..db import get_db
from ..security import current_user, workspace_context
from ..services.tenancy import WorkspaceCtx
from ..services import agent as agent_service
from ..services import speech, translate
from ..services.speech import SpeechError, whisper_language_hint
from ..services.voice_audio import VoiceAudioError, validate_audio_upload

router = APIRouter(prefix="/voice", tags=["voice"])

LANG_PATTERN = re.compile(r"^(en|hi|mr)$")


async def _transcribe_upload(file: UploadFile, language: str | None) -> dict:
    data = await file.read()
    try:
        suffix = validate_audio_upload(data, file.filename, file.content_type)
    except VoiceAudioError as exc:
        raise HTTPException(422, exc.message)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        return speech.transcribe(path, language)
    except SpeechError as exc:
        if exc.code == "unavailable":
            raise HTTPException(503, exc.message)
        if exc.code in ("invalid_audio", "provider_failed"):
            raise HTTPException(422, exc.message)
        raise HTTPException(503, exc.message)
    finally:
        os.unlink(path)


def _resolve_stt_language(user: models.User, override: str | None) -> str | None:
    if override and LANG_PATTERN.match(override):
        return override
    return whisper_language_hint(user.language) or None


@router.post("/transcribe", response_model=schemas.TranscribeOut)
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    user: models.User = Depends(current_user),
):
    hint = _resolve_stt_language(user, language)
    result = await _transcribe_upload(file, hint)
    return {
        "text": result["text"],
        "detected_language": result.get("language") or "",
        "language_hint": hint or "",
    }


@router.post("/chat", response_model=schemas.VoiceChatOut)
async def voice_chat(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    ctx: WorkspaceCtx = Depends(workspace_context),
):
    hint = _resolve_stt_language(user, language)
    result = await _transcribe_upload(file, hint)
    transcript = (result.get("text") or "").strip()
    if not transcript:
        raise HTTPException(
            422,
            "Could not hear anything in that recording. Speak clearly for at least 2 seconds and try again.",
        )
    detected = result.get("language") or ""
    out = agent_service.handle_message(
        db,
        user,
        transcript,
        source="voice",
        voice_meta={"detected_language": detected, "language_hint": hint or ""},
        ctx=ctx,
    )
    return {
        **out,
        "transcript": transcript,
        "detected_language": detected,
        "language_hint": hint or "",
    }


@router.post("/translate")
def translate_text(body: schemas.TranslateIn, user: models.User = Depends(current_user)):
    return {"text": translate.translate(body.text, body.target)}
