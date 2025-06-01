import os
from typing import Dict
import memory_manager as mm

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
except Exception:  # pragma: no cover - optional
    Update = None
    ApplicationBuilder = None
    class _Stub:
        DEFAULT_TYPE = object

    ContextTypes = _Stub

SESSION_EMOTIONS: Dict[int, str] = {}


async def emotion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tag = " ".join(context.args)
    SESSION_EMOTIONS[update.effective_chat.id] = tag
    await update.message.reply_text(f"Emotion tag set to {tag}")


async def recall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send back recent memory fragments matching a tag."""
    tag = " ".join(context.args)
    if not tag:
        await update.message.reply_text("Usage: /recall <tag>")
        return
    frags = mm.search_by_tags([tag], limit=3)
    if not frags:
        await update.message.reply_text("No memories found")
        return
    text = "\n---\n".join(f["text"] for f in frags)
    await update.message.reply_text(text)


def run_bot(token: str) -> None:
    if ApplicationBuilder is None:
        raise RuntimeError("python-telegram-bot not installed")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("emotion", emotion))
    app.add_handler(CommandHandler("recall", recall))
    app.run_polling()


if __name__ == "__main__":  # pragma: no cover - manual
    tok = os.getenv("TELEGRAM_TOKEN")
    if tok:
        run_bot(tok)
