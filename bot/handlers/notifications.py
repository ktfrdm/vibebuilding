"""«Да, приду!» / «Увы, не смогу» — ответ на «Сможешь прийти?»."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.storage import meetings, participants


async def _notify_organizer_confirm(bot, meeting_id: str, participant_name: str, confirmed: bool) -> None:
    """Уведомляет организатора об ответе на «Сможешь прийти?»."""
    m = meetings.get(meeting_id)
    if not m:
        return
    who = (participant_name or "Участник").strip() or "Участник"
    try:
        if confirmed:
            await bot.send_message(m.creator_user_id, f"✅ {who} подтвердил(а) участие в «{m.title}».")
        else:
            await bot.send_message(m.creator_user_id, f"❌ {who} не сможет прийти на «{m.title}».")
    except Exception:
        pass


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
    # Добавляем выбранный слот, чтобы участник попадал в «Придут» при открытии сводки
    if m.chosen_slot_id is not None and m.chosen_slot_id not in p.chosen_slot_ids:
        p.chosen_slot_ids = list(p.chosen_slot_ids) + [m.chosen_slot_id]
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    await query.edit_message_text(
        f"🎉 Встречаемся! {m.title} — {slot_label}. Место: {m.place or 'уточните в чате'}"
    )
    await _notify_organizer_confirm(context.bot, meeting_id, p.first_name, confirmed=True)
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
    await query.edit_message_text("😊 Жаль, надеемся увидеться в следующий раз!")
    await _notify_organizer_confirm(context.bot, meeting_id, p.first_name, confirmed=False)
    await query.answer()
