"""Telegram interface. Run: python -m bot.telegram_bot

Link your account first: in the web app click "Link Telegram", then send /link CODE to the bot.
Text and voice notes both go to the same assistant that the web app uses.
"""
import asyncio
import logging
import os
import tempfile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from app import models
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.services import agent, speech

logging.basicConfig(level=logging.INFO)


def _user_for_chat(db, chat_id: int):
    return db.query(models.User).filter_by(telegram_chat_id=str(chat_id)).first()


def _run_agent(chat_id: int, text: str):
    db = SessionLocal()
    try:
        user = _user_for_chat(db, chat_id)
        if not user:
            return None
        return agent.handle_message(db, user, text)
    finally:
        db.close()


def _resolve(chat_id: int, action_id: int, approve: bool) -> dict:
    db = SessionLocal()
    try:
        user = _user_for_chat(db, chat_id)
        if not user:
            return {"error": "Account not linked"}
        return agent.resolve_pending(db, user, action_id, approve)
    finally:
        db.close()


async def _reply(update: Update, result):
    if result is None:
        await update.message.reply_text("Your account is not linked. Send /link CODE (get the code in the web app).")
        return
    await update.message.reply_text(result["reply"] or "Done.")
    for action in result["pending"]:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Approve", callback_data=f"ok:{action.id}"),
            InlineKeyboardButton("Reject", callback_data=f"no:{action.id}"),
        ]])
        await update.message.reply_text(action.summary, reply_markup=kb)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm your creator assistant. Link your account with /link CODE, then message me or send a voice note.")


async def link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /link CODE")
        return
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(telegram_link_code=ctx.args[0].upper()).first()
        if not user:
            await update.message.reply_text("That code is not valid. Generate a new one in the web app.")
            return
        user.telegram_chat_id = str(update.effective_chat.id)
        user.telegram_link_code = None
        db.commit()
        await update.message.reply_text(f"Linked to {user.name or user.email}. You can start now.")
    finally:
        db.close()


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result = await asyncio.to_thread(_run_agent, update.effective_chat.id, update.message.text)
    await _reply(update, result)


async def on_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        path = tmp.name
    try:
        await file.download_to_drive(path)
        heard = await asyncio.to_thread(speech.transcribe, path)
    except speech.SpeechError as exc:
        await update.message.reply_text(exc.message)
        return
    finally:
        if os.path.exists(path):
            os.unlink(path)
    if not heard["text"]:
        await update.message.reply_text("I could not hear anything in that voice note.")
        return
    await update.message.reply_text(f"Heard: {heard['text']}")
    result = await asyncio.to_thread(_run_agent, update.effective_chat.id, heard["text"])
    await _reply(update, result)


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    verdict, action_id = query.data.split(":")
    out = await asyncio.to_thread(_resolve, query.message.chat_id, int(action_id), verdict == "ok")
    if "error" in out:
        await query.edit_message_text(f"Could not complete: {out['error']}")
    elif out["status"] == "rejected":
        await query.edit_message_text("Cancelled.")
    else:
        r = out["result"]
        if "error" in r:
            await query.edit_message_text(f"Failed: {r['error']}")
        else:
            links = "\n".join(r.get("links", {}).values())
            await query.edit_message_text(
                f"Booked. Ref {r['reference']} ({r['provider']}).\n{r['pickup']} to {r['drop']} at {r['when']}\n{links}")


def main():
    if not settings.telegram_bot_token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env (create a bot with @BotFather).")
    Base.metadata.create_all(bind=engine)
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("link", link))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    app.run_polling()


if __name__ == "__main__":
    main()
