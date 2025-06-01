import os
from typing import Dict
from pathlib import Path
import memory_manager as mm
import ocr_log_export as oe
import privilege_lint as pl
import reflection_digest as rd

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


async def export_ocr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export OCR log from last day and send as CSV."""
    pl.audit_use("telegram", "export_ocr")
    path = oe.export_last_day_csv()
    if not path:
        await update.message.reply_text("No OCR entries")
        return
    with open(path, "rb") as f:
        await update.message.reply_document(f, filename=os.path.basename(path))


async def digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the most recent reflection digest."""
    pl.audit_use("telegram", "digest")
    path = rd.generate_digest()
    if not path:
        await update.message.reply_text("No digest available")
        return
    txt = Path(path).read_text(encoding="utf-8")
    await update.message.reply_text(txt)


def run_bot(token: str) -> None:
    if ApplicationBuilder is None:
        raise RuntimeError("python-telegram-bot not installed")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("emotion", emotion))
    app.add_handler(CommandHandler("recall", recall))
    app.add_handler(CommandHandler("export_ocr", export_ocr))
    app.add_handler(CommandHandler("digest", digest))
    app.run_polling()


if __name__ == "__main__":  # pragma: no cover - manual
    tok = os.getenv("TELEGRAM_TOKEN")
    if tok:
        run_bot(tok)
