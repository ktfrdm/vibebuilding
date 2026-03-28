"""Handler /start — сброс состояния, главное меню или deep link."""
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.inline import start_inline_keyboard_first
from bot.storage import clear_user_state

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    logger.info("cmd_start: user_id=%s, args=%s", user_id, context.args or [])
    args = context.args or []
    arg0 = (args[0] or "").strip() if args else ""

    # Deep link сводки: /start svodka_xxx (не путать со сбросом)
    if arg0.startswith("svodka_"):
        from bot.handlers.organizer import cmd_svodka
        context.args = [arg0.replace("svodka_", "", 1)]
        await cmd_svodka(update, context)
        return

    # Deep link участника: /start meeting_xxx
    if arg0.startswith("meeting_"):
        from bot.handlers.participant import handle_participant_start
        await handle_participant_start(update, context)
        return

    clear_user_state(user_id)
    await update.message.reply_text(
        "👋 Привет! Я помогу собрать друзей и согласовать время встречи.",
        reply_markup=start_inline_keyboard_first(),
    )
