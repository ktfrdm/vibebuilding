"""Участник: deep link, слоты, ответы."""
import html
import logging
from typing import List, Optional

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatters import participant_tag
from bot.handlers.organizer import send_meeting_summary
from bot.keyboards.inline import organizer_choose_slot_keyboard, participant_slots_keyboard
from bot.storage import Meeting, ParticipantData, meetings, participants, participant_selection

logger = logging.getLogger(__name__)


def _slot_labels(slots: list, indices: list[int]) -> str:
    """Подписи слотов по индексам."""
    parts = []
    for i in indices:
        if 0 <= i < len(slots):
            s = slots[i]
            label = f"{s.get('date', '')} {s.get('time', '')}".strip()
            if label:
                parts.append(label)
    return ", ".join(parts)


async def _notify_organizer_new_response(
    bot, meeting_id: str, participant_name: str, is_decline: bool,
    chosen_slot_ids: Optional[List[int]] = None,
) -> None:
    """Уведомляет организатора о новом ответе участника."""
    m = meetings.get(meeting_id)
    if not m:
        logger.warning(
            "Уведомление организатору пропущено: встреча %s не найдена (возможно, другой экземпляр бота). Запустите только один экземпляр через run_bot.sh.",
            meeting_id,
        )
        return
    creator_id = m.creator_user_id
    who = participant_name or "Участник"
    bot_info = await bot.get_me()
    username = bot_info.username or "bot"
    link = f"https://t.me/{username}?start=meeting_{meeting_id}"
    if is_decline:
        text = f"📋 {who} не сможет прийти на «{m.title}».\n\nОткрой ссылку для сводки:\n{link}"
    else:
        slot_text = ""
        if chosen_slot_ids:
            labels = _slot_labels(m.slots, chosen_slot_ids)
            if labels:
                slot_text = f" Выбрал слоты: {labels}."
        text = f"📋 {who} ответил на приглашение «{m.title}».{slot_text}\n\nОткрой ссылку для сводки:\n{link}"
    try:
        await bot.send_message(creator_id, text)
    except Exception as e:
        logger.warning("Не удалось отправить уведомление организатору: %s", e)


async def _notify_organizer_late_join(
    bot, meeting_id: str, participant_name: str, is_coming: bool
) -> None:
    """Уведомляет организатора об ответе участника, перешедшего по ссылке после назначения встречи."""
    m = meetings.get(meeting_id)
    if not m:
        return
    who = (participant_name or "Участник").strip() or "Участник"
    bot_info = await bot.get_me()
    username = bot_info.username or "bot"
    link = f"https://t.me/{username}?start=meeting_{meeting_id}"
    if is_coming:
        text = f"📋 {who} ответил позже: придёт на «{m.title}».\n\nОткрой ссылку для сводки:\n{link}"
    else:
        text = f"📋 {who} ответил позже: не сможет прийти на «{m.title}».\n\nОткрой ссылку для сводки:\n{link}"
    try:
        await bot.send_message(m.creator_user_id, text)
    except Exception as e:
        logger.warning("Не удалось отправить уведомление организатору: %s", e)


def _extract_meeting_id(args: list):
    if not args or not args[0].strip().startswith("meeting_"):
        return None
    return args[0].strip().replace("meeting_", "").strip()


async def handle_participant_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вызывается из cmd_start при deep link /start meeting_xxx."""
    if not update.message:
        return
    meeting_id = _extract_meeting_id(context.args or [])
    if not meeting_id:
        return
    mid = f"m_{meeting_id}" if not meeting_id.startswith("m_") else meeting_id
    m = meetings.get(mid)
    if not m:
        await update.message.reply_text("Встреча не найдена или уже завершена.")
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    user_id = update.effective_user.id if update.effective_user else 0
    if m.status == "time_chosen":
        await send_meeting_summary(context.bot, mid, chat_id, user_id=user_id)
        return
    if user_id == m.creator_user_id:
        await _show_organizer_summary(update, context, m)
    else:
        key = (mid, user_id)
        participant_selection[key] = set()
        await update.message.reply_text(
            f"📅 {m.title}\n\nОтметь удобные слоты или нажми «Увы, не смогу», если не получится",
            reply_markup=participant_slots_keyboard(m.slots, mid, set()),
        )


def _count_slot_votes(m: Meeting) -> list[tuple[int, int]]:
    replied_keys = [k for k, p in participants.items() if k[0] == m.id and p.status == "replied"]
    total = len(replied_keys)
    counts = []
    for i in range(len(m.slots)):
        ok = sum(1 for k in replied_keys if i in participants[k].chosen_slot_ids)
        counts.append((ok, total))
    return counts


def _order_slots_by_votes(slots: list, counts: list[tuple[int, int]]) -> tuple[list, list, list[int]]:
    if not slots or not counts:
        return slots, counts, list(range(len(slots)))
    indexed = []
    for i in range(len(slots)):
        ok, tot = counts[i] if i < len(counts) else (0, 0)
        key = (0 if (tot and ok == tot) else 1, -ok)
        indexed.append((key, i, slots[i], (ok, tot)))
    indexed.sort(key=lambda x: x[0])
    ordered_slots = [x[2] for x in indexed]
    ordered_counts = [x[3] for x in indexed]
    original_indices = [x[1] for x in indexed]
    return ordered_slots, ordered_counts, original_indices


async def _show_organizer_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, m: Meeting) -> None:
    if not update.message:
        return
    if m.status == "time_chosen":
        slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
        label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
        await update.message.reply_text(f"Встреча уже назначена: {label}")
        return
    counts = _count_slot_votes(m)
    ordered_slots, ordered_counts, idx_map = _order_slots_by_votes(m.slots, counts)
    declined = sum(1 for k, p in participants.items() if k[0] == m.id and p.status == "declined")
    title_esc = html.escape(m.title)
    lines = [f"{title_esc} — ответы:", ""]
    if ordered_counts:
        lines.append("📊 По слотам (удобно/всего ответивших):")
        for i, s in enumerate(ordered_slots):
            ok, tot = ordered_counts[i] if i < len(ordered_counts) else (0, 0)
            label = html.escape(f"{s.get('date', '')} {s.get('time', '')}".strip())
            orig_idx = idx_map[i] if i < len(idx_map) else i
            # Кто проголосовал за этот слот
            voters = [
                participant_tag(k[1], participants[k].first_name)
                for k, p in participants.items()
                if k[0] == m.id and p.status == "replied" and orig_idx in p.chosen_slot_ids
            ]
            voters_str = ", ".join(voters) if voters else "—"
            lines.append(f"  • {label}: {ok}/{tot}")
            lines.append(f"    Кто: {voters_str}")
    if declined:
        lines.append(f"\nОтказались: {declined}")
    # MVP: счётчик «ещё не ответили» недоступен — в participants попадают только replied/declined
    lines.append("\n⏰ Выбери итоговое время:")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=organizer_choose_slot_keyboard(ordered_slots, m.id, ordered_counts, idx_map),
        parse_mode="HTML",
    )


async def slot_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await query.answer()
        return
    _, meeting_id, slot_idx = parts
    slot_idx = int(slot_idx)
    m = meetings.get(meeting_id)
    if not m:
        await query.answer("Встреча не найдена")
        return
    await query.answer()
    user_id = update.effective_user.id if update.effective_user else 0
    key = (meeting_id, user_id)
    sel = participant_selection.get(key, set())
    if slot_idx in sel:
        sel.discard(slot_idx)
    else:
        sel.add(slot_idx)
    participant_selection[key] = sel
    await query.edit_message_reply_markup(
        reply_markup=participant_slots_keyboard(m.slots, meeting_id, sel),
    )


async def decline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    name = (update.effective_user.first_name or "").strip() if update.effective_user else ""
    key = (meeting_id, user_id)
    participants[key] = ParticipantData(status="declined", chosen_slot_ids=[], pending_confirm=False, first_name=name)
    participant_selection.pop(key, None)
    await query.edit_message_text("🙏 Спасибо, что ответил!")
    await _notify_organizer_new_response(context.bot, meeting_id, name, is_decline=True, chosen_slot_ids=None)


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    name = (update.effective_user.first_name or "").strip() if update.effective_user else ""
    key = (meeting_id, user_id)
    sel = participant_selection.get(key, set())
    participants[key] = ParticipantData(status="replied", chosen_slot_ids=list(sel), pending_confirm=False, first_name=name)
    participant_selection.pop(key, None)
    await query.edit_message_text(
        "👍 Супер, записал! Дождёмся, когда все ответят — тогда напишем, когда встречаемся"
    )
    await _notify_organizer_new_response(
        context.bot, meeting_id, name, is_decline=False, chosen_slot_ids=list(sel)
    )


async def late_join_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Новый участник нажал «Да, приду!» после назначения встречи."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    name = (update.effective_user.first_name or "").strip() if update.effective_user else ""
    key = (meeting_id, user_id)
    if key in participants:
        await query.edit_message_text("Ты уже ответил.")
        return
    m = meetings.get(meeting_id)
    if not m or m.status != "time_chosen" or m.chosen_slot_id is None:
        await query.edit_message_text("Встреча не найдена или ещё не назначена.")
        return
    participants[key] = ParticipantData(
        status="replied",
        chosen_slot_ids=[m.chosen_slot_id],
        pending_confirm=False,
        first_name=name,
    )
    slot = m.slots[m.chosen_slot_id] or {}
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    await query.edit_message_text(
        f"👍 Записал! Встречаемся — {slot_label}. Место: {m.place or 'уточните в чате'}"
    )
    await _notify_organizer_late_join(context.bot, meeting_id, name, is_coming=True)


async def late_join_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Новый участник нажал «Увы, не смогу» после назначения встречи."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    name = (update.effective_user.first_name or "").strip() if update.effective_user else ""
    key = (meeting_id, user_id)
    if key in participants:
        await query.edit_message_text("Ты уже ответил.")
        return
    m = meetings.get(meeting_id)
    if not m or m.status != "time_chosen":
        await query.edit_message_text("Встреча не найдена или ещё не назначена.")
        return
    participants[key] = ParticipantData(
        status="declined",
        chosen_slot_ids=[],
        pending_confirm=False,
        first_name=name,
    )
    await query.edit_message_text("🙏 Спасибо, что ответил!")
    await _notify_organizer_late_join(context.bot, meeting_id, name, is_coming=False)
