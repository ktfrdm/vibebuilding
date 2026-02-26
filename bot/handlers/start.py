"""Handler /start — сброс состояния, главное меню или deep link participant."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.inline import start_reply_keyboard
from bot.storage import clear_user_state


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    clear_user_state(user_id)
    args = context.args or []
    # Deep link: /start meeting_xxx
    if args and args[0].strip().startswith("meeting_"):
        from bot.handlers.participant import handle_participant_start
        await handle_participant_start(update, context)
        return
    await update.message.reply_text(
        "👋 Привет! Я помогу собрать друзей и согласовать время встречи.\n\n"
        "Нажми «Давай соберёмся!» чтобы начать.",
        reply_markup=start_reply_keyboard(),
    )
