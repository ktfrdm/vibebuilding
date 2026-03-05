"""Общие команды: /help, /logs."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.logs_destination import set_logs_chat_id


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Я помогаю согласовывать время встречи. Нажми /start и выбери «Давай соберёмся!» — "
        "создашь встречу, получишь ссылку для участников. Участники отметят удобные слоты, "
        "ты выберешь итоговое время — я разошлю уведомления."
    )


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """В группе/супергруппе сохраняет chat_id как получатель логов бота."""
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Команда /logs доступна только в группе. Добавьте бота в группу «Vibe logs» и отправьте там /logs.")
        return
    set_logs_chat_id(chat.id)
    await update.message.reply_text("Эта группа настроена для логов бота.")
