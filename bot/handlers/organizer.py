"""Поток организатора: storage-based state (python-telegram-bot)."""
import html
import logging
import random
import string
from typing import Optional

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from bot.formatters import participant_tag
from bot.keyboards.inline import (
    can_you_come_keyboard,
    confirm_place_keyboard,
    invite_keyboard,
    invite_keyboard_for_organizer,
    late_join_keyboard,
    skip_keyboard,
    slots_confirm_keyboard,
    start_reply_keyboard,
)
from bot.services.llm import filter_past_slots, parse_options
from bot.storage import (
    Meeting,
    clear_user_state,
    get_user_state,
    get_user_step,
    meetings,
    participants,
    set_user_state,
    update_user_state,
)

SLOTS_PROMPT = (
    "Какие варианты времени предложить участникам? Напиши одним сообщением, "
    "например: «суббота 12:00, 15:00, 18:00» или «в эту субботу», «25 февраля вечером» — поймём"
)

START_BUTTONS = ("Давай соберёмся!", "Давай соберемся!", "Собрать друзей")
SVODKA_BUTTONS = ("Статус", "📋 Статус")


def _generate_meeting_id() -> str:
    return "m_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))


logger = logging.getLogger(__name__)


def _user_id(update: Update) -> int:
    u = update.effective_user
    return u.id if u else 0


def _get_message_text(update: Update) -> Optional[str]:
    """Текст сообщения: message.text или message.caption (фото с подписью).
    Учитывает также edited_message.
    """
    msg = update.message or update.edited_message
    if not msg:
        return None
    return (msg.text or msg.caption or "").strip() or None


async def cmd_svodka(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать статус: /svodka, кнопка «Статус» или deep link start=svodka_xxx."""
    if not update.message:
        return
    uid = _user_id(update)
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    meeting_id_arg = (args[0] or "").strip() if args else None

    if meeting_id_arg:
        mid = f"m_{meeting_id_arg}" if not meeting_id_arg.startswith("m_") else meeting_id_arg
        m = meetings.get(mid)
        if not m:
            await update.message.reply_text("Встреча не найдена или уже завершена.")
            return
        if m.status == "time_chosen":
            await send_meeting_summary(context.bot, mid, chat_id, user_id=uid)
        elif uid == m.creator_user_id:
            from bot.handlers.participant import _show_organizer_summary
            await _show_organizer_summary(update, context, m)
        else:
            await send_meeting_summary(context.bot, mid, chat_id, user_id=uid)
        return

    my_meetings = [m for m in meetings.values() if m.creator_user_id == uid]
    if not my_meetings:
        await update.message.reply_text("У тебя пока нет встреч. Нажми «Давай соберёмся!» чтобы создать.")
        return
    m = my_meetings[-1]
    if m.status == "time_chosen":
        await send_meeting_summary(context.bot, m.id, chat_id)
    else:
        from bot.handlers.participant import _show_organizer_summary
        await _show_organizer_summary(update, context, m)


async def _handle_svodka(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    """Обработка кнопки «Статус» — вызывает cmd_svodka."""
    await cmd_svodka(update, context)


async def create_meeting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _user_id(update)
    clear_user_state(uid)
    set_user_state(uid, "title")
    # Сворачиваем reply-клавиатуру перед шагом с inline-кнопками
    await update.message.reply_text(
        "Начинаем создавать встречу.",
        reply_markup=ReplyKeyboardRemove(selective=True),
    )
    await update.message.reply_text(
        "💬 Как назовём нашу встречу? Например: «Кофе», «Ужин в пятницу». Можно пропустить!",
        reply_markup=skip_keyboard(),
    )


async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message or update.edited_message
    if not msg:
        logger.warning("process_text: ни message, ни edited_message")
        return
    text = _get_message_text(update)
    uid = _user_id(update)
    step = get_user_step(uid)
    logger.info("process_text: uid=%s step=%s text=%r", uid, step, text[:50] if text else None)
    if not text:
        if step in ("title", "slots", "place"):
            await msg.reply_text("Отправь, пожалуйста, текст.")
        return
    if text in START_BUTTONS:
        await create_meeting_start(update, context)
        return
    if text in SVODKA_BUTTONS:
        await _handle_svodka(update, context, uid)
        return
    if step == "title":
        await _handle_title(update, uid)
    elif step == "slots":
        await _handle_slots(update, uid)
    elif step == "place":
        await _handle_place(update, context, uid)
    else:
        await msg.reply_text(
            'Нажми «Давай соберёмся!» чтобы создать встречу или «Статус» для просмотра.',
            reply_markup=start_reply_keyboard(),
        )


async def _handle_title(update: Update, uid: int) -> None:
    msg = update.message or update.edited_message
    if not msg:
        return
    title = _get_message_text(update) or "Встреча"
    logger.info("_handle_title: uid=%s title=%r", uid, title[:50] if title else None)
    update_user_state(uid, title=title)
    set_user_state(uid, "slots", {"title": title})
    await msg.reply_text(SLOTS_PROMPT)


async def _handle_slots(update: Update, uid: int) -> None:
    if not update.message:
        return
    text = (update.message.text or "").strip()
    result = parse_options(text)
    if not result.get("ok"):
        await update.message.reply_text(
            "🤔 Хм, не совсем понял. Напиши варианты времени попроще, например: «суббота 12:00, 15:00, 18:00»"
        )
        return
    slots = result.get("slots", [])
    if not slots:
        await update.message.reply_text("Не удалось извлечь слоты. Попробуй ещё раз.")
        return
    slots_list_raw = []
    for s in slots:
        if isinstance(s, dict):
            slots_list_raw.append(s)
        else:
            slots_list_raw.append({"date": str(s), "time": "", "datetime": ""})
    slots_list, past = filter_past_slots(slots_list_raw)
    if not slots_list:
        await update.message.reply_text(
            "Нельзя назначить встречу в прошлом. Укажи даты и время в будущем, например: «суббота 12:00, 15:00» или «25 февраля вечером»."
        )
        return
    state = get_user_state(uid)
    title = (state.get("data") or {}).get("title", "Встреча")
    update_user_state(uid, slots=slots_list)
    set_user_state(uid, "slots_confirm", {"title": title, "slots": slots_list})
    lines = [f"{i+1}. {s.get('date', '')} {s.get('time', '')}".strip() for i, s in enumerate(slots_list)]
    header = "Некоторые слоты были в прошлом — убрал. Вот что получается:\n" if past else "✨ Отлично! Вот что получается:\n"
    await update.message.reply_text("\u200b", reply_markup=ReplyKeyboardRemove(selective=True))
    await update.message.reply_text(
        header + "\n".join(lines) + "\n\nПодходит?",
        reply_markup=slots_confirm_keyboard(),
    )


async def _handle_place(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    if not update.message:
        return
    state = get_user_state(uid)
    data = state.get("data") or {}
    meeting_id = data.get("meeting_id")
    if not meeting_id:
        clear_user_state(uid)
        return
    m = meetings.get(meeting_id)
    if not m:
        await update.message.reply_text("Встреча не найдена")
        clear_user_state(uid)
        return
    place = (update.message.text or "").strip() or "уточните в чате"
    m.place = place
    clear_user_state(uid)
    await _send_notifications(context.bot, meeting_id, place)
    await update.message.reply_text("Готово! Уведомления отправлены.")


async def skip_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    uid = _user_id(update)
    if get_user_step(uid) != "title":
        await query.answer()
        return
    set_user_state(uid, "slots", {"title": "Встреча"})
    await query.edit_message_text(SLOTS_PROMPT)
    await query.answer()


async def slots_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    uid = _user_id(update)
    if get_user_step(uid) != "slots_confirm":
        await query.answer()
        return
    state = get_user_state(uid)
    data = state.get("data") or {}
    title = data.get("title", "Встреча")
    slots = data.get("slots", [])
    meeting_id = _generate_meeting_id()
    creator_id = uid
    chat_id = query.message.chat.id if query.message else 0
    m = Meeting(
        id=meeting_id,
        title=title,
        slots=slots,
        status="created",
        creator_user_id=creator_id,
        chat_id=chat_id,
    )
    meetings[meeting_id] = m
    clear_user_state(uid)
    bot = context.bot
    bot_info = await bot.get_me()
    username = bot_info.username or "bot"
    chat = query.message.chat if query.message else None
    is_group = chat and chat.type in ("group", "supergroup")
    if is_group:
        await query.edit_message_text(
            "✅ Готово! Ниже — приглашение для участников.",
        )
        invite_text = (
            f"📅 Планируется встреча «{title}».\n\n"
            f"Ответь на приглашение — нажми кнопку ниже и выбери удобное время."
        )
        await bot.send_message(
            chat_id,
            invite_text,
            reply_markup=invite_keyboard(meeting_id, username, title=title),
        )
        await bot.send_message(
            creator_id,
            "✅ Приглашение опубликовано в чате. Участники могут нажать кнопку и ответить.",
            reply_markup=invite_keyboard_for_organizer(username, meeting_id, title),
        )
    else:
        mid = meeting_id.replace("m_", "") if meeting_id.startswith("m_") else meeting_id
        link = f"https://t.me/{username}?start=meeting_{mid}"
        await query.edit_message_text(
            f"✅ Готово! Нажми кнопку ниже, чтобы отправить приглашение участникам.\n\n"
            f"Ссылка: {link}",
            reply_markup=invite_keyboard_for_organizer(username, meeting_id, title),
        )
    await query.answer()


async def slots_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    uid = _user_id(update)
    if get_user_step(uid) != "slots_confirm":
        await query.answer()
        return
    state = get_user_state(uid)
    data = state.get("data") or {}
    title = data.get("title", "Встреча")
    set_user_state(uid, "slots", {"title": title})
    await query.edit_message_text(SLOTS_PROMPT)
    await query.answer()


async def choose_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    uid = _user_id(update)
    if not m or uid != m.creator_user_id:
        await query.answer("Встреча не найдена")
        return
    m.chosen_slot_id = slot_idx
    m.status = "time_chosen"
    set_user_state(uid, "place", {"meeting_id": meeting_id})
    chat_id = query.message.chat.id if query.message else 0
    await context.bot.send_message(
        chat_id, "\u200b", reply_markup=ReplyKeyboardRemove(selective=True)
    )
    await query.edit_message_text(
        "📍 Где собираемся? Напиши место или нажми «Пропустить» — уточните потом в чате",
        reply_markup=confirm_place_keyboard(),
    )
    await query.answer()


async def place_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    uid = _user_id(update)
    if get_user_step(uid) != "place":
        await query.answer()
        return
    state = get_user_state(uid)
    meeting_id = (state.get("data") or {}).get("meeting_id")
    if not meeting_id:
        clear_user_state(uid)
        await query.answer()
        return
    m = meetings.get(meeting_id)
    if not m:
        clear_user_state(uid)
        await query.answer()
        return
    m.place = "уточните в чате"
    clear_user_state(uid)
    await _send_notifications(context.bot, meeting_id, m.place)
    await query.edit_message_text("Готово! Уведомления отправлены.")
    chat_id = query.message.chat.id if query.message else 0
    await context.bot.send_message(
        chat_id, "👇", reply_markup=start_reply_keyboard()
    )
    await query.answer()


async def show_svodka_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка inline-кнопки «Статус» — только просмотр ответивших, без выбора времени."""
    query = update.callback_query
    if not query:
        return
    _, meeting_id = (query.data or "").split(":", 1)
    await query.answer()
    uid = _user_id(update)
    chat_id = query.message.chat.id if query.message else 0
    m = meetings.get(meeting_id)
    if not m:
        await query.edit_message_text("Встреча не найдена или уже завершена.")
        return
    if m.status == "time_chosen":
        await send_meeting_summary(context.bot, meeting_id, chat_id, user_id=uid)
    elif uid == m.creator_user_id:
        from bot.handlers.participant import _send_organizer_summary_view_only
        await _send_organizer_summary_view_only(context.bot, chat_id, m)
    else:
        await send_meeting_summary(context.bot, meeting_id, chat_id, user_id=uid)


async def choose_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка inline-кнопки «Выбрать время» — показать кнопки выбора итогового слота."""
    query = update.callback_query
    if not query:
        return
    _, meeting_id = (query.data or "").split(":", 1)
    await query.answer()
    uid = _user_id(update)
    chat_id = query.message.chat.id if query.message else 0
    m = meetings.get(meeting_id)
    if not m:
        await query.edit_message_text("Встреча не найдена или уже завершена.")
        return
    if m.status == "time_chosen":
        await send_meeting_summary(context.bot, meeting_id, chat_id, user_id=uid)
    elif uid == m.creator_user_id:
        from bot.handlers.participant import _send_organizer_choose_time
        await _send_organizer_choose_time(context.bot, chat_id, m)
    else:
        await send_meeting_summary(context.bot, meeting_id, chat_id, user_id=uid)


async def organizer_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _user_id(update)
    if get_user_step(uid) in ("title", "slots", "place"):
        await update.message.reply_text("Отправь, пожалуйста, текст.")


async def send_meeting_summary(
    bot, meeting_id: str, chat_id: int, user_id: Optional[int] = None
) -> None:
    """Отправляет итоги встречи в указанный чат. Если user_id передан и не в participants — спрашивает «Придёшь?»."""
    m = meetings.get(meeting_id)
    if not m or m.status != "time_chosen":
        return
    place = m.place or "уточните в чате"
    ask_late_join = (
        user_id is not None and (meeting_id, user_id) not in participants
    )
    await _send_meeting_summary_to_chat(
        bot, meeting_id, place, chat_id, ask_late_join=ask_late_join
    )


async def _send_meeting_summary_to_chat(
    bot, meeting_id: str, place: str, chat_id: int, ask_late_join: bool = False
) -> None:
    """Отправляет итоги встречи в указанный чат."""
    m = meetings.get(meeting_id)
    if not m:
        return
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    coming = []
    pending = []
    declined_tags = []
    for k, p in participants.items():
        if k[0] != meeting_id:
            continue
        user_id = k[1]
        tag = participant_tag(user_id, p.first_name)
        if p.status == "declined":
            declined_tags.append(tag)
        elif p.status == "replied":
            if m.chosen_slot_id in p.chosen_slot_ids:
                coming.append(tag)
            else:
                pending.append(tag)
    title_esc = html.escape(m.title)
    place_esc = html.escape(place or "уточните в чате")
    slot_esc = html.escape(slot_label)
    lines = [
        f"📋 Встречаемся!" + (f" «{title_esc}»" if m.title.strip() else ""),
        "",
        f"🕐 Время: {slot_esc}",
        f"📍 Место: {place_esc}",
        "",
    ]
    if coming:
        lines.append("👍 Придут: " + ", ".join(coming))
    if pending:
        lines.append("❓ Ожидают ответа «Сможешь прийти?»: " + ", ".join(pending))
    if declined_tags:
        lines.append("👋 Не смогут: " + ", ".join(declined_tags))
    if not coming and not pending and not declined_tags:
        lines.append("Пока нет ответов.")
    if ask_late_join:
        lines.append("")
        lines.append("Придёшь?")
    text = "\n".join(lines)
    reply_markup = late_join_keyboard(meeting_id) if ask_late_join else None
    try:
        await bot.send_message(
            chat_id, text, parse_mode="HTML", reply_markup=reply_markup
        )
    except Exception:
        pass


async def _send_organizer_summary(bot, meeting_id: str, place: str) -> None:
    """Отправляет организатору итоги после подтверждения места."""
    m = meetings.get(meeting_id)
    if not m:
        return
    await _send_meeting_summary_to_chat(bot, meeting_id, place, m.creator_user_id)


def _format_meeting_notification(m: Meeting, slot_label: str, place: str) -> str:
    """Форматирует уведомление о встрече как сводку."""
    title_esc = html.escape(m.title.strip() or "Встреча")
    place_esc = html.escape(place or "уточните в чате")
    slot_esc = html.escape(slot_label)
    return (
        f"📋 Встречаемся!" + (f" «{title_esc}»" if title_esc != "Встреча" else "") + "\n\n"
        f"🕐 Время: {slot_esc}\n"
        f"📍 Место: {place_esc}"
    )


async def _send_notifications(bot, meeting_id: str, place: str) -> None:
    m = meetings.get(meeting_id)
    if not m:
        return
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    replied = [k for k, p in participants.items() if k[0] == meeting_id and p.status == "replied"]
    notification_text = _format_meeting_notification(m, slot_label, place)
    for k in replied:
        user_id = k[1]
        sel = participants[k].chosen_slot_ids
        if m.chosen_slot_id in sel:
            await bot.send_message(
                user_id,
                notification_text,
                parse_mode="HTML",
            )
        else:
            participants[k].pending_confirm = True
            confirm_text = (
                f"{notification_text}\n\n"
                f"❓ Ты выбирал другие слоты. Сможешь прийти?"
            )
            await bot.send_message(
                user_id,
                confirm_text,
                parse_mode="HTML",
                reply_markup=can_you_come_keyboard(meeting_id),
            )
    await _send_organizer_summary(bot, meeting_id, place)
