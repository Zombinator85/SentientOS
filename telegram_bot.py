import os
from typing import Dict

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
except Exception:  # pragma: no cover - optional
    Update = None
    ApplicationBuilder = None

SESSION_EMOTIONS: Dict[int, str] = {}


async def emotion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tag = " ".join(context.args)
    SESSION_EMOTIONS[update.effective_chat.id] = tag
    await update.message.reply_text(f"Emotion tag set to {tag}")


def run_bot(token: str) -> None:
    if ApplicationBuilder is None:
        raise RuntimeError("python-telegram-bot not installed")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("emotion", emotion))
    app.run_polling()


if __name__ == "__main__":  # pragma: no cover - manual
    tok = os.getenv("TELEGRAM_TOKEN")
    if tok:
        run_bot(tok)
