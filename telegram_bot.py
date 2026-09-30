import os
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from instagram_bot import (
    ACTIVITY_HISTORY_FILE,
    STATS_FILE,
    load_json,
)


def _admin_id():
    value = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
    return str(value)


def _authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and _admin_id() and str(user.id) == _admin_id())


async def _deny(update: Update):
    if update.effective_message:
        await update.effective_message.reply_text("Unauthorized.")


def build_application(start_callback, stop_callback, status_callback):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set.")

    app = ApplicationBuilder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        await update.effective_message.reply_text(
            "Instagram Bot\n\n"
            "/run - run with saved users\n"
            "/collect <location> <number> - collect new users\n"
            "/status - worker status\n"
            "/stats - current counters\n"
            "/activity - recent activity\n"
            "/stop - request a graceful stop"
        )

    async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        ok, message = start_callback("saved", None, None)
        await update.effective_message.reply_text(message)

    async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)

        if len(context.args) < 2:
            await update.effective_message.reply_text(
                "Usage: /collect <location> <number>\nExample: /collect Shiraz 1"
            )
            return

        location = " ".join(context.args[:-1]).strip()
        try:
            index = int(context.args[-1])
        except ValueError:
            await update.effective_message.reply_text("Location number must be an integer.")
            return

        ok, message = start_callback("collect", location, index)
        await update.effective_message.reply_text(message)

    async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        await update.effective_message.reply_text(stop_callback())

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        await update.effective_message.reply_text(status_callback())

    async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        data = load_json(STATS_FILE, {})
        await update.effective_message.reply_text(
            "Stats\n"
            f"Follow: {data.get('follow', 0)}\n"
            f"Like (Story and Post): {data.get('like (Story and Post)', 0)}\n"
            f"Story seen: {data.get('story_seen', 0)}\n"
            f"Processed accounts: {len(data.get('processed_accounts', []))}"
        )

    async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _authorized(update):
            return await _deny(update)
        data = load_json(ACTIVITY_HISTORY_FILE, {})
        if isinstance(data, dict):
            items = []
            for date_key, sessions in data.items():
                if isinstance(sessions, list):
                    for session in sessions:
                        items.append((date_key, session))
            items = items[-5:]
            lines = ["Recent activity:"]
            for date_key, session in items:
                lines.append(
                    f"{date_key} | {session.get('start', '?')} → "
                    f"{session.get('stop', '?')} | {session.get('status', '?')}"
                )
            await update.effective_message.reply_text("\n".join(lines))
        else:
            await update.effective_message.reply_text("No activity history found.")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("run", run))
    app.add_handler(CommandHandler("collect", collect))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("activity", activity))

    return app
