"""Участник: deep link, слоты, ответы."""
import html
import logging
from typing import List, Optional

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatters import format_meeting_notification, participant_tag, shift_entities, utf16_len
from bot.handlers.organizer import send_meeting_summary
from bot.keyboards.inline import (
    organizer_choose_slot_keyboard,
    organizer_notification_keyboard,
    participant_slots_keyboard,
)
from bot.storage import Meeting, ParticipantData, meetings, participants, participant_selection
from bot.telegram_logger import send_log_event

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
    bot, meeting_id: str, participant_user_id: int, participant_name: str,
    is_decline: bool, chosen_slot_ids: Optional[List[int]] = None,
) -> None:
    """Уведомляет организатора о новом ответе участника."""
    m = meetings.get(meeting_id)
    if not m:
        logger.warning(
            "Уведомление организатору пропущено: встреча %s не найдена.",
            meeting_id,
        )
        return
    creator_id = m.creator_user_id
    who_tag = participant_tag(participant_user_id, participant_name)
    title_esc = html.escape(m.title)
    if is_decline:
        text = f"📋 {who_tag} не сможет прийти на «{title_esc}»."
    else:
        slot_text = ""
        if chosen_slot_ids:
            labels = _slot_labels(m.slots, chosen_slot_ids)
            if labels:
                slot_text = f" Выбрал слоты: {labels}."
        text = f"📋 {who_tag} ответил на приглашение «{title_esc}».{slot_text}"
    try:
        await bot.send_message(
            creator_id, text, parse_mode="HTML",
            reply_markup=organizer_notification_keyboard(meeting_id),
        )
    except Exception as e:
        logger.warning("Не удалось отправить уведомление организатору: %s", e)


async def _notify_organizer_late_join(
    bot, meeting_id: str, participant_user_id: int, participant_name: str,
    is_coming: bool,
) -> None:
    """Уведомляет организатора об ответе участника, перешедшего по ссылке после назначения встречи."""
    m = meetings.get(meeting_id)
    if not m:
        return
    who_tag = participant_tag(participant_user_id, participant_name)
    title_esc = html.escape(m.title)
    if is_coming:
        text = f"📋 {who_tag} ответил позже: придёт на «{title_esc}»."
    else:
        text = f"📋 {who_tag} ответил позже: не сможет прийти на «{title_esc}»."
    try:
        await bot.send_message(
            m.creator_user_id, text, parse_mode="HTML",
            reply_markup=organizer_notification_keyboard(meeting_id),
        )
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
        u = update.effective_user
        uid = u.id if u else 0
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="participant_start",
            error_type="MeetingNotFoundByLink",
            error_message="Встреча не найдена или уже завершена (участник по ссылке)",
        )
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
        slots_preview = ", ".join(
            f"{s.get('date', '')} {s.get('time', '')}".strip()
            for s in m.slots
            if f"{s.get('date', '')} {s.get('time', '')}".strip()
        )
        summary = (
            f"📅 «{html.escape(m.title)}»\n\n"
            f"Варианты времени: {html.escape(slots_preview) or '—'}\n\n"
            f"Отметь удобные слоты и нажми кнопку «Готово» внизу."
        )
        await update.message.reply_text(
            summary,
            reply_markup=participant_slots_keyboard(m.slots, mid, set()),
            parse_mode="HTML",
        )
        u = update.effective_user
        await send_log_event(
            context.bot,
            "participant_opened",
            user_id=user_id,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            title=m.title,
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


def _build_organizer_summary_text_only(m: Meeting) -> str:
    """Текст сводки для просмотра (без кнопок выбора времени)."""
    counts = _count_slot_votes(m)
    ordered_slots, ordered_counts, idx_map = _order_slots_by_votes(m.slots, counts)
    declined_tags = [
        participant_tag(k[1], participants[k].first_name)
        for k, p in participants.items()
        if k[0] == m.id and p.status == "declined"
    ]
    title_esc = html.escape(m.title)
    lines = [f"{title_esc} — ответы:", ""]
    if ordered_counts:
        lines.append("📊 По слотам (удобно/всего ответивших):")
        for i, s in enumerate(ordered_slots):
            ok, tot = ordered_counts[i] if i < len(ordered_counts) else (0, 0)
            label = html.escape(f"{s.get('date', '')} {s.get('time', '')}".strip())
            orig_idx = idx_map[i] if i < len(idx_map) else i
            voters = [
                participant_tag(k[1], participants[k].first_name)
                for k, p in participants.items()
                if k[0] == m.id and p.status == "replied" and orig_idx in p.chosen_slot_ids
            ]
            voters_str = ", ".join(voters) if voters else "—"
            lines.append(f"  • {label}: {ok}/{tot}")
            lines.append(f"    Кто: {voters_str}")
    if declined_tags:
        lines.append(f"\nОтказались: {', '.join(declined_tags)}")
    return "\n".join(lines)


def _build_organizer_choose_time_keyboard(m: Meeting) -> object:
    """Клавиатура выбора итогового времени."""
    counts = _count_slot_votes(m)
    ordered_slots, ordered_counts, idx_map = _order_slots_by_votes(m.slots, counts)
    return organizer_choose_slot_keyboard(ordered_slots, m.id, ordered_counts, idx_map)


def _build_organizer_summary_text_and_keyboard(m: Meeting) -> tuple[str, object]:
    """Строит текст и клавиатуру статуса организатора (голосование). Используется при /svodka и Reply «Статус»."""
    text = _build_organizer_summary_text_only(m) + "\n\n⏰ Выбери итоговое время:"
    markup = _build_organizer_choose_time_keyboard(m)
    return text, markup


async def _send_organizer_summary_to_chat(bot, chat_id: int, m: Meeting) -> None:
    """Отправляет сводку голосования организатору в указанный чат (с кнопками выбора времени)."""
    if m.status == "time_chosen":
        slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
        label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
        await bot.send_message(chat_id, f"Встреча уже назначена: {label}")
        return
    text, markup = _build_organizer_summary_text_and_keyboard(m)
    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")


async def _send_organizer_summary_view_only(bot, chat_id: int, m: Meeting) -> None:
    """Отправляет только текст сводки (просмотр ответивших), без кнопок выбора времени."""
    if m.status == "time_chosen":
        slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
        label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
        await bot.send_message(chat_id, f"Встреча уже назначена: {label}")
        return
    text = _build_organizer_summary_text_only(m)
    await bot.send_message(chat_id, text, parse_mode="HTML")


async def _send_organizer_choose_time(bot, chat_id: int, m: Meeting) -> None:
    """Отправляет сообщение с кнопками выбора итогового времени."""
    if m.status == "time_chosen":
        slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
        label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
        await bot.send_message(chat_id, f"Встреча уже назначена: {label}")
        return
    markup = _build_organizer_choose_time_keyboard(m)
    await bot.send_message(
        chat_id,
        "⏰ Выбери итоговое время:",
        reply_markup=markup,
        parse_mode="HTML",
    )


async def _show_organizer_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, m: Meeting) -> None:
    if not update.message:
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    await _send_organizer_summary_to_chat(context.bot, chat_id, m)


async def slot_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        await query.answer()
        return
    _, meeting_id, slot_idx_str = parts
    try:
        slot_idx = int(slot_idx_str)
    except ValueError:
        await query.answer()
        return
    m = meetings.get(meeting_id)
    if not m:
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=update.effective_user.id if update.effective_user else 0,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="slot_toggle",
            error_type="MeetingNotFoundCallback",
            error_message="Встреча не найдена при переключении слота",
        )
        await query.answer("Встреча не найдена")
        return
    if not (0 <= slot_idx < len(m.slots)):
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=u.id if u else 0,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="slot_toggle",
            error_type="InvalidSlotIndex",
            error_message=f"Индекс слота {slot_idx} вне диапазона (всего {len(m.slots)})",
        )
        await query.answer("Неверный слот")
        return
    user_id = update.effective_user.id if update.effective_user else 0
    key = (meeting_id, user_id)
    sel = participant_selection.get(key, set())
    if slot_idx in sel:
        sel.discard(slot_idx)
    else:
        sel.add(slot_idx)
    participant_selection[key] = sel
    await query.answer()
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
    m = meetings.get(meeting_id)
    participants[key] = ParticipantData(status="declined", chosen_slot_ids=[], pending_confirm=False, first_name=name)
    participant_selection.pop(key, None)
    title_esc = html.escape(m.title) if m else html.escape(meeting_id)
    await query.edit_message_text(
        f"🙏 Спасибо, что ответил!\n\n«{title_esc}» — ты не сможешь прийти.",
        parse_mode="HTML",
    )
    await _notify_organizer_new_response(
        context.bot, meeting_id, user_id, name, is_decline=True, chosen_slot_ids=None
    )
    u = update.effective_user
    title = m.title if m else meeting_id
    await send_log_event(
        context.bot,
        "participant_declined",
        user_id=user_id,
        username=u.username if u else None,
        first_name=u.first_name if u else None,
        title=title,
    )


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
    m = meetings.get(meeting_id)
    participants[key] = ParticipantData(status="replied", chosen_slot_ids=list(sel), pending_confirm=False, first_name=name)
    participant_selection.pop(key, None)
    chosen_labels = _slot_labels(m.slots, list(sel)) if m else ""
    title_esc = html.escape(m.title) if m else "Встреча"
    result = (
        f"👍 Записал!\n\n"
        f"«{title_esc}» — твои слоты: {html.escape(chosen_labels) or '—'}\n\n"
        f"Дождёмся, когда все ответят — тогда напишем, когда встречаемся."
    )
    await query.edit_message_text(result, parse_mode="HTML")
    await _notify_organizer_new_response(
        context.bot, meeting_id, user_id, name, is_decline=False, chosen_slot_ids=list(sel)
    )
    u = update.effective_user
    title = m.title if m else "Встреча"
    await send_log_event(
        context.bot,
        "participant_replied",
        user_id=user_id,
        username=u.username if u else None,
        first_name=u.first_name if u else None,
        title=title,
        chosen_slots_count=len(sel),
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
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=user_id,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="late_join_yes",
            error_type="ParticipantAlreadyReplied",
            error_message="Участник нажал «Приду» повторно",
        )
        await query.edit_message_text("Ты уже ответил.")
        return
    m = meetings.get(meeting_id)
    if not m or m.status != "time_chosen" or m.chosen_slot_id is None:
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=user_id,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="late_join_yes",
            error_type="MeetingNotFoundOrNotFinalized",
            error_message="Встреча не найдена или ещё не назначена (прийти)",
        )
        await query.edit_message_text("Встреча не найдена или ещё не назначена.")
        return
    participants[key] = ParticipantData(
        status="replied",
        chosen_slot_ids=[m.chosen_slot_id],
        pending_confirm=False,
        first_name=name,
    )
    slot = m.slots[m.chosen_slot_id] or {}
    place = m.place or "уточните в чате"
    text_part, entities = format_meeting_notification(m, slot, place)
    prefix = "👍 Записал!\n\n"
    full_text = prefix + text_part
    if entities:
        entities = shift_entities(entities, utf16_len(prefix))
    await query.edit_message_text(
        full_text,
        entities=entities,
        parse_mode=None if entities else "HTML",
    )
    await _notify_organizer_late_join(context.bot, meeting_id, user_id, name, is_coming=True)


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
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=user_id,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="late_join_no",
            error_type="ParticipantAlreadyReplied",
            error_message="Участник нажал «Не смогу» повторно",
        )
        await query.edit_message_text("Ты уже ответил.")
        return
    m = meetings.get(meeting_id)
    if not m or m.status != "time_chosen":
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=user_id,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="late_join_no",
            error_type="MeetingNotFoundOrNotFinalized",
            error_message="Встреча не найдена или ещё не назначена (не смогу)",
        )
        await query.edit_message_text("Встреча не найдена или ещё не назначена.")
        return
    participants[key] = ParticipantData(
        status="declined",
        chosen_slot_ids=[],
        pending_confirm=False,
        first_name=name,
    )
    await query.edit_message_text("🙏 Спасибо, что ответил!")
    await _notify_organizer_late_join(context.bot, meeting_id, user_id, name, is_coming=False)
