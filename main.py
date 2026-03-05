"""Точка входа бота (python-telegram-bot)."""
import logging
import os
import sys

from telegram import BotCommand

# Блокировка: только один локальный экземпляр бота.
# В продакшне (Railway) предполагается один процесс, поэтому блокировка по файлу безвредна.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_LOCK_FILE = os.path.join(_script_dir, ".bot.lock")

try:
    import fcntl

    _lock_fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            "Другой экземпляр бота уже запущен. Используйте ./run_bot.sh для перезапуска.",
            file=sys.stderr,
        )
        sys.exit(1)
except ImportError:
    _lock_fd = None  # Windows: fcntl недоступен, пропускаем проверку
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import BOT_TOKEN, LOG_LEVEL
from bot.handlers import common, notifications, organizer, participant, start
from bot.queue import PerUserUpdateProcessor
from bot.storage import get_user_step
from bot.telegram_logger import send_log_event

logging.basicConfig(
    level=getattr(logging, (LOG_LEVEL or "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN or TELEGRAM_BOT_TOKEN not set in .env")


async def post_init(application):
    await application.bot.set_my_commands(
        [
            BotCommand(command="start", description="Сбросить и начать заново"),
            BotCommand(command="svodka", description="Статус встречи"),
        ]
    )


async def error_handler(update, context):
    logging.exception("Unhandled error: %s", context.error)
    # Немедленно отправить лог об ошибке в группу Vibe logs (если настроена).
    bot = context.application.bot if context.application else None
    if bot:
        err = context.error
        where = "user" if (update and update.effective_user) else "service"
        payload = {
            "where": where,
            "error_type": type(err).__name__,
            "error_message": str(err),
            "exception": err,
        }
        if where == "user" and update and update.effective_user:
            u = update.effective_user
            payload["user_id"] = u.id
            payload["username"] = u.username
            payload["first_name"] = u.first_name
            try:
                step = get_user_step(u.id)
                if step and step != "idle":
                    payload["step"] = step
            except Exception:
                pass
        await send_log_event(bot, "error", **payload)
    if update and update.effective_message:
        await update.effective_message.reply_text("Что-то пошло не так. Нажми /start")
    elif update and update.callback_query:
        await update.callback_query.answer("Ошибка. Нажми /start.")


def main():
    processor = PerUserUpdateProcessor(max_concurrent_updates=32)
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(processor)
        .build()
    )
    app.add_error_handler(error_handler)

    # Порядок критичен: start (с deep link), help, callbacks, текст организатора, fallback
    app.add_handler(CommandHandler("start", start.cmd_start))
    app.add_handler(CommandHandler("svodka", organizer.cmd_svodka))
    app.add_handler(CommandHandler("logs", common.cmd_logs))
    app.add_handler(CommandHandler("help", common.cmd_help))
    app.add_handler(
        CallbackQueryHandler(participant.slot_toggle, pattern="^slot_toggle:")
    )
    app.add_handler(CallbackQueryHandler(participant.decline, pattern="^decline:"))
    app.add_handler(CallbackQueryHandler(participant.done, pattern="^done:"))
    app.add_handler(CallbackQueryHandler(organizer.start_meeting_callback, pattern="^start_meeting$"))
    app.add_handler(CallbackQueryHandler(organizer.main_svodka_callback, pattern="^main_svodka$"))
    app.add_handler(CallbackQueryHandler(organizer.skip_title, pattern="^skip$"))
    app.add_handler(CallbackQueryHandler(organizer.slots_confirmed, pattern="^slots_ok$"))
    app.add_handler(CallbackQueryHandler(organizer.slots_edit, pattern="^slots_edit$"))
    app.add_handler(CallbackQueryHandler(organizer.choose_slot, pattern="^choose_slot:"))
    app.add_handler(CallbackQueryHandler(organizer.place_skip, pattern="^place_skip$"))
    app.add_handler(
        CallbackQueryHandler(notifications.confirm_yes, pattern="^confirm_yes:")
    )
    app.add_handler(
        CallbackQueryHandler(notifications.confirm_no, pattern="^confirm_no:")
    )
    app.add_handler(
        CallbackQueryHandler(participant.late_join_yes, pattern="^late_join_yes:")
    )
    app.add_handler(
        CallbackQueryHandler(participant.late_join_no, pattern="^late_join_no:")
    )
    app.add_handler(
        CallbackQueryHandler(organizer.show_svodka_callback, pattern="^show_svodka:")
    )
    app.add_handler(
        CallbackQueryHandler(organizer.choose_time_callback, pattern="^choose_time:")
    )
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & ~filters.COMMAND,
            organizer.process_text,
        )
    )
    app.add_handler(MessageHandler(filters.ALL, organizer.organizer_non_text))

    # Режим работы: polling (локально) или webhook (Railway/прод).
    # Webhook включается: USE_WEBHOOK=1 или задан один из URL (Railway задаёт RAILWAY_PUBLIC_DOMAIN).
    port = int(os.getenv("PORT", "8080"))
    base_url = (
        os.getenv("WEBHOOK_URL")
        or os.getenv("RAILWAY_STATIC_URL")
        or (f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}" if os.getenv("RAILWAY_PUBLIC_DOMAIN") else None)
    )
    use_webhook = (
        os.getenv("USE_WEBHOOK", "").lower() in ("1", "true", "yes")
        or bool(base_url)
    )

    if use_webhook:
        if not base_url:
            raise RuntimeError(
                "WEBHOOK_URL, RAILWAY_STATIC_URL or RAILWAY_PUBLIC_DOMAIN must be set in webhook mode"
            )
        base_url = base_url.rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url
        url_path = BOT_TOKEN
        webhook_url = f"{base_url}/{url_path}"
        logging.info("Starting webhook on port %s with URL %s", port, webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=url_path,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        logging.info("Starting bot in polling mode")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
