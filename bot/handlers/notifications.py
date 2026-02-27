"""«Да, приду!» / «Увы, не смогу» — ответ на «Сможешь прийти?»."""
import html

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatters import participant_tag
from bot.keyboards.inline import organizer_notification_keyboard
from bot.storage import meetings, participants


async def _notify_organizer_confirm(
    bot, meeting_id: str, participant_user_id: int, participant_name: str, confirmed: bool
) -> None:
    """Уведомляет организатора об ответе на «Сможешь прийти?»."""
    m = meetings.get(meeting_id)
    if not m:
        return
    who_tag = participant_tag(participant_user_id, participant_name)
    title_esc = html.escape(m.title)
    try:
        if confirmed:
            await bot.send_message(
                m.creator_user_id,
                f"✅ {who_tag} подтвердил(а) участие в «{title_esc}».",
                parse_mode="HTML",
                reply_markup=organizer_notification_keyboard(meeting_id),
            )
        else:
            await bot.send_message(
                m.creator_user_id,
                f"❌ {who_tag} не сможет прийти на «{title_esc}».",
                parse_mode="HTML",
                reply_markup=organizer_notification_keyboard(meeting_id),
            )
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
    from bot.handlers.organizer import _format_meeting_notification
    place = m.place or "уточните в чате"
    text = _format_meeting_notification(m, slot_label, place)
    await query.edit_message_text(text, parse_mode="HTML")
    await _notify_organizer_confirm(
        context.bot, meeting_id, user_id, p.first_name, confirmed=True
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
    await query.edit_message_text("😊 Жаль, надеемся увидеться в следующий раз!")
    await _notify_organizer_confirm(
        context.bot, meeting_id, user_id, p.first_name, confirmed=False
    )
    await query.answer()
