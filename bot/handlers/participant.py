"""Участник: deep link, слоты, ответы."""
from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.inline import organizer_choose_slot_keyboard, participant_slots_keyboard
from bot.storage import Meeting, ParticipantData, meetings, participants, participant_selection


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
    user_id = update.effective_user.id if update.effective_user else 0
    if user_id == m.creator_user_id:
        await _show_organizer_summary(update, context, m)
    else:
        key = (mid, user_id)
        participant_selection[key] = set()
        await update.message.reply_text(
            f"{m.title}\n\nОтметь удобные слоты или нажми «Увы, не смогу», если не получится",
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
    lines = [f"{m.title} — ответы:", ""]
    if ordered_counts:
        lines.append("По слотам (удобно/всего ответивших):")
        for i, s in enumerate(ordered_slots):
            ok, tot = ordered_counts[i] if i < len(ordered_counts) else (0, 0)
            label = f"{s.get('date', '')} {s.get('time', '')}".strip()
            lines.append(f"  • {label}: {ok}/{tot}")
    if declined:
        lines.append(f"\nОтказались: {declined}")
    # MVP: счётчик «ещё не ответили» недоступен — в participants попадают только replied/declined
    lines.append("\nВыбери итоговое время:")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=organizer_choose_slot_keyboard(ordered_slots, m.id, ordered_counts, idx_map),
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
    key = (meeting_id, user_id)
    participants[key] = ParticipantData(status="declined", chosen_slot_ids=[], pending_confirm=False)
    participant_selection.pop(key, None)
    await query.edit_message_text("Спасибо, что ответил!")


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    _, meeting_id = (query.data or "").split(":", 1)
    user_id = update.effective_user.id if update.effective_user else 0
    key = (meeting_id, user_id)
    sel = participant_selection.get(key, set())
    participants[key] = ParticipantData(status="replied", chosen_slot_ids=list(sel), pending_confirm=False)
    participant_selection.pop(key, None)
    await query.edit_message_text(
        "Супер, записал! Дождёмся, когда все ответят — тогда напишем, когда встречаемся"
    )
