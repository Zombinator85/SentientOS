import os
import datetime
from typing import Dict
from pathlib import Path
import memory_manager as mm
import ocr_log_export as oe
import privilege_lint as pl
import reflection_digest as rd
import reflection_log_cli as rlc
import zipfile

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
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


async def search_reflect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Search reflections by keyword and return top matches."""
    keyword = " ".join(context.args)
    if not keyword:
        await update.message.reply_text("Usage: /search_reflect <keyword>")
        return
    matches = list(rlc.search_entries(keyword, context=20))[:3]
    if not matches:
        await update.message.reply_text("No reflections found")
        return
    text = "\n".join(f"[{d}] {s}" for d, s in matches)
    await update.message.reply_text(text)


async def bulk_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send zipped OCR CSV exports from the last N days."""
    days = int(context.args[0]) if context.args else 1
    pl.audit_use("telegram", "bulk_export")
    log_dir = oe.OCR_LOG.parent
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    files = []
    for fp in log_dir.glob("ocr_export_*.csv"):
        if fp.stat().st_mtime >= cutoff.timestamp():
            files.append(fp)
    if not files:
        await update.message.reply_text("No CSV files found")
        return
    zip_path = log_dir / "bulk_export.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in files:
            z.write(f, f.name)
    with open(zip_path, "rb") as f:
        await update.message.reply_document(f, filename="bulk_export.zip")


def run_bot(token: str) -> None:
    if ApplicationBuilder is None:
        raise RuntimeError("python-telegram-bot not installed")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("emotion", emotion))
    app.add_handler(CommandHandler("recall", recall))
    app.add_handler(CommandHandler("export_ocr", export_ocr))
    app.add_handler(CommandHandler("digest", digest))
    app.add_handler(CommandHandler("search_reflect", search_reflect))
    app.add_handler(CommandHandler("bulk_export", bulk_export))
    app.run_polling()


if __name__ == "__main__":  # pragma: no cover - manual
    tok = os.getenv("TELEGRAM_TOKEN")
    if tok:
        run_bot(tok)
