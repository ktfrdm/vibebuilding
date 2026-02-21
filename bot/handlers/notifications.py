"""«Да, приду!» / «Увы, не смогу» — ответ на «Сможешь прийти?»."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.storage import meetings, participants


async def confirm_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    key = (meeting_id, user_id)
    p = participants.get(key)
    if not p or not p.pending_confirm:
        await query.answer()
        return
    p.pending_confirm = False
    m = meetings.get(meeting_id)
    if not m:
        await query.answer()
        return
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    await query.edit_message_text(
        f"Встречаемся! {m.title} — {slot_label}. Место: {m.place or 'уточните в чате'}"
    )
    await query.answer()


async def confirm_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    key = (meeting_id, user_id)
    p = participants.get(key)
    if not p:
        await query.answer()
        return
    p.pending_confirm = False
    p.status = "declined"
    await query.edit_message_text("Жаль, надеемся увидеться в следующий раз!")
    await query.answer()
