"""Общие команды: /help."""
from telegram import Update
from telegram.ext import ContextTypes


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Я помогаю согласовывать время встречи. Нажми /start и выбери «Давай соберёмся!» — "
        "создашь встречу, получишь ссылку для участников. Участники отметят удобные слоты, "
        "ты выберешь итоговое время — я разошлю уведомления."
    )
