"""Поток организатора: storage-based state (python-telegram-bot)."""
import html
import logging
import random
import string
import time
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from bot.formatters import format_meeting_notification, participant_tag
from bot.keyboards.inline import (
    can_you_come_keyboard,
    confirm_place_keyboard,
    invite_keyboard,
    invite_keyboard_for_organizer,
    invite_keyboard_private_organizer,
    late_join_keyboard,
    skip_keyboard,
    slots_confirm_keyboard,
    start_inline_keyboard,
)
from bot.chat_context import (
    ORGANIZER_TITLE_PROMPT,
    append_group_organizer_hint,
    is_group_like_chat,
)
from bot.services.llm import filter_past_slots, parse_options
from bot.storage import (
    Meeting,
    clear_user_state,
    get_meetings_by_creator,
    get_participants_for_meeting,
    get_user_state,
    get_user_step,
    meetings,
    organizer_flow_start,
    participants,
    set_user_state,
    update_user_state,
)
from bot.telegram_logger import send_log_event

SLOTS_PROMPT = (
    "🕐 Какие варианты времени предложить участникам? Напиши одним сообщением, "
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
            u = update.effective_user
            await send_log_event(
                context.bot,
                "error",
                where="user",
                user_id=uid,
                username=u.username if u else None,
                first_name=u.first_name if u else None,
                step="start_link",
                error_type="MeetingNotFoundByLink",
                error_message="Встреча не найдена или уже завершена",
                user_input=meeting_id_arg,
            )
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

    my_meetings = get_meetings_by_creator(uid)
    if not my_meetings:
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="svodka",
            error_type="NoMeetingsYet",
            error_message="Организатор открыл статус, встреч пока нет",
        )
        await update.message.reply_text(
            "📭 У тебя пока нет встреч. Нажми «Давай соберёмся!» внизу или в меню, чтобы создать."
        )
        return
    m = my_meetings[0]
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
    organizer_flow_start[uid] = time.time()
    u = update.effective_user
    await send_log_event(
        context.bot,
        "organizer_start",
        user_id=uid,
        username=u.username if u else None,
        first_name=u.first_name if u else None,
    )
    chat = update.effective_chat
    await update.message.reply_text(
        append_group_organizer_hint(ORGANIZER_TITLE_PROMPT, chat),
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
            await msg.reply_text("✏️ Отправь, пожалуйста, текст.")
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
        await _handle_slots(update, context, uid)
    elif step == "place":
        await _handle_place(update, context, uid)
    else:
        if is_group_like_chat(msg.chat):
            await msg.reply_text(
                "💡 Чтобы начать встречу в этом чате, нажми «Давай соберёмся!» у сообщения бота выше "
                "или ответь на сообщение бота командой /start.",
            )
        else:
            await msg.reply_text(
                "👇 Создать встречу или посмотреть статус:",
                reply_markup=start_inline_keyboard(),
            )


async def _handle_title(update: Update, uid: int) -> None:
    msg = update.message or update.edited_message
    if not msg:
        return
    title = _get_message_text(update) or "Встреча"
    logger.info("_handle_title: uid=%s title=%r", uid, title[:50] if title else None)
    update_user_state(uid, title=title)
    set_user_state(uid, "slots", {"title": title})
    await msg.reply_text(append_group_organizer_hint(SLOTS_PROMPT, msg.chat))


async def _handle_slots(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    if not update.message:
        return
    text = (update.message.text or "").strip()
    result = parse_options(text)
    if not result.get("ok"):
        err_msg = result.get("error", "Не удалось распознать слоты")
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="slots",
            error_type="SlotsNotUnderstood",
            error_message=err_msg,
            user_input=text,
        )
        await update.message.reply_text(
            "🤔 Хм, не совсем понял. Напиши варианты времени попроще, например: «суббота 12:00, 15:00, 18:00»"
        )
        return
    slots = result.get("slots", [])
    if not slots:
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="slots",
            error_type="SlotsEmpty",
            error_message="LLM вернул ok, но слотов нет",
            user_input=text,
        )
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
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="slots",
            error_type="AllSlotsInPast",
            error_message="Все слоты в прошлом",
            user_input=text,
        )
        await update.message.reply_text(
            "Нельзя назначить встречу в прошлом. Укажи даты и время в будущем, например: «суббота 12:00, 15:00» или «25 февраля вечером»."
        )
        return
    if past:
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="slots",
            error_type="SomeSlotsInPast",
            error_message=f"Убрано слотов в прошлом: {len(past)}, осталось: {len(slots_list)}",
            user_input=text,
        )
    state = get_user_state(uid)
    title = (state.get("data") or {}).get("title", "Встреча")
    update_user_state(uid, slots=slots_list)
    set_user_state(uid, "slots_confirm", {"title": title, "slots": slots_list})
    lines = [f"{i+1}. {s.get('date', '')} {s.get('time', '')}".strip() for i, s in enumerate(slots_list)]
    header = (
        "⚠️ Некоторые слоты были в прошлом — убрал. Вот что получается:\n"
        if past
        else "✨ Отлично! Вот что получается:\n"
    )
    body = header + "\n".join(lines) + "\n\nПодходит?"
    await update.message.reply_text(
        append_group_organizer_hint(body, update.message.chat),
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
        u = update.effective_user
        place_text = (update.message.text or "").strip()
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="place",
            error_type="MeetingNotFoundInFlow",
            error_message="Встреча не найдена при вводе места",
            user_input=place_text or None,
        )
        await update.message.reply_text("Встреча не найдена")
        clear_user_state(uid)
        return
    place = (update.message.text or "").strip() or "уточните в чате"
    m.place = place
    meetings[meeting_id] = m
    clear_user_state(uid)
    await _send_notifications(context.bot, meeting_id, place)
    started = organizer_flow_start.pop(uid, None)
    duration_sec = (time.time() - started) if started else None
    participants_count = sum(1 for _k, p in get_participants_for_meeting(meeting_id) if p.status == "replied")
    await send_log_event(
        context.bot,
        "organizer_notifications_sent",
        title=m.title,
        participants_count=participants_count,
        duration_sec=duration_sec,
    )
    await update.message.reply_text(
        "Готово! Уведомления отправлены.",
        reply_markup=start_inline_keyboard(),
    )


async def skip_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    uid = _user_id(update)
    if get_user_step(uid) != "title":
        await query.answer()
        return
    set_user_state(uid, "slots", {"title": "Встреча"})
    chat = query.message.chat if query.message else None
    await query.edit_message_text(append_group_organizer_hint(SLOTS_PROMPT, chat))
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
    mid = meeting_id.replace("m_", "") if meeting_id.startswith("m_") else meeting_id
    link = f"https://t.me/{username}?start=meeting_{mid}"
    invite_text = (
        f"📣 Планируется встреча «{title}».\n\n"
        f"{link}\n\n"
        f"Нажми кнопку ниже, чтобы ответить и выбрать удобное время."
    )
    invite_text_private_organizer = (
        f"✉️ Встреча «{title}» готова — осталось позвать людей.\n\n"
        f"Нажми «Переслать приглашение» и выбери чат или собеседника: "
        f"им уйдёт короткое сообщение со ссылкой, по ней сразу открывается выбор удобного времени.\n\n"
        f"{link}\n\n"
        f"«Ответить на приглашение» — чтобы пройти тот же путь, что и участник."
    )
    if is_group:
        await query.edit_message_text(
            "✅ Готово! Ниже — приглашение для участников.",
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
        await query.edit_message_text(
            invite_text_private_organizer,
            reply_markup=invite_keyboard_private_organizer(meeting_id, username, title=title),
        )
    await send_log_event(
        bot,
        "organizer_meeting_created",
        title=title,
        slots_count=len(slots),
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
    chat = query.message.chat if query.message else None
    await query.edit_message_text(append_group_organizer_hint(SLOTS_PROMPT, chat))
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
    _, meeting_id, slot_idx_str = parts
    try:
        slot_idx = int(slot_idx_str)
    except ValueError:
        await query.answer()
        return
    m = meetings.get(meeting_id)
    uid = _user_id(update)
    if not m or uid != m.creator_user_id:
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="choose_slot",
            error_type="MeetingNotFoundOrNotCreator",
            error_message="Встреча не найдена или пользователь не организатор",
        )
        await query.answer("Встреча не найдена")
        return
    if not (0 <= slot_idx < len(m.slots)):
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="choose_slot",
            error_type="InvalidSlotIndex",
            error_message=f"Индекс слота {slot_idx} вне диапазона (всего {len(m.slots)})",
        )
        await query.answer("Неверный слот")
        return
    m.chosen_slot_id = slot_idx
    m.status = "time_chosen"
    meetings[meeting_id] = m
    set_user_state(uid, "place", {"meeting_id": meeting_id})
    chat_id = query.message.chat.id if query.message else 0
    place_chat = query.message.chat if query.message else None
    await query.edit_message_text(
        append_group_organizer_hint(
            "📍 Где собираемся? Напиши место или нажми «Пропустить» — уточните потом в чате",
            place_chat,
        ),
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
    meetings[meeting_id] = m
    clear_user_state(uid)
    await _send_notifications(context.bot, meeting_id, m.place)
    creator_uid = m.creator_user_id
    started = organizer_flow_start.pop(creator_uid, None)
    duration_sec = (time.time() - started) if started else None
    participants_count = sum(1 for _k, p in get_participants_for_meeting(meeting_id) if p.status == "replied")
    await send_log_event(
        context.bot,
        "organizer_notifications_sent",
        title=m.title,
        participants_count=participants_count,
        duration_sec=duration_sec,
    )
    await query.edit_message_text("✅ Готово! Уведомления отправлены.")
    await query.answer()


async def start_meeting_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline-кнопка «Давай соберёмся!» — начать создание встречи."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    uid = _user_id(update)
    chat_id = query.message.chat.id if query.message else 0
    clear_user_state(uid)
    set_user_state(uid, "title")
    organizer_flow_start[uid] = time.time()
    u = update.effective_user
    await send_log_event(
        context.bot,
        "organizer_start",
        user_id=uid,
        username=u.username if u else None,
        first_name=u.first_name if u else None,
    )
    chat = query.message.chat if query.message else None
    await context.bot.send_message(
        chat_id,
        append_group_organizer_hint(ORGANIZER_TITLE_PROMPT, chat),
        reply_markup=skip_keyboard(),
    )


async def main_svodka_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline-кнопка «Статус» — список встреч организатора."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    uid = _user_id(update)
    chat_id = query.message.chat.id if query.message else 0
    my_meetings = get_meetings_by_creator(uid)
    if not my_meetings:
        await context.bot.send_message(
            chat_id,
            "📭 У тебя пока нет встреч. Нажми «Давай соберёмся!», чтобы создать.",
            reply_markup=start_inline_keyboard(),
        )
        return
    m = my_meetings[0]
    from bot.handlers.participant import _send_organizer_summary_to_chat
    await _send_organizer_summary_to_chat(context.bot, chat_id, m)


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
        u = update.effective_user
        await send_log_event(
            context.bot,
            "error",
            where="user",
            user_id=uid,
            username=u.username if u else None,
            first_name=u.first_name if u else None,
            step="choose_time",
            error_type="MeetingNotFoundCallback",
            error_message="Встреча не найдена или уже завершена (choose_time)",
        )
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
        await update.message.reply_text("✏️ Отправь, пожалуйста, текст.")


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


def _participant_display_name(first_name: str) -> str:
    """Имя для отображения в сводке (без HTML)."""
    return (first_name or "Участник").strip() or "Участник"


async def _send_meeting_summary_to_chat(
    bot, meeting_id: str, place: str, chat_id: int, ask_late_join: bool = False
) -> None:
    """Отправляет итоги встречи в указанный чат. Время — в формате Telegram (date_time) для добавления в календарь."""
    m = meetings.get(meeting_id)
    if not m:
        return
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    coming_names = []
    pending_names = []
    declined_names = []
    for _k, p in get_participants_for_meeting(meeting_id):
        name = _participant_display_name(p.first_name)
        if p.status == "declined":
            declined_names.append(name)
        elif p.status == "replied":
            if m.chosen_slot_id in p.chosen_slot_ids:
                coming_names.append(name)
            else:
                pending_names.append(name)
    header_text, header_entities = format_meeting_notification(m, slot, place)
    extra = []
    if coming_names:
        extra.append("Придут: " + ", ".join(coming_names))
    if pending_names:
        extra.append("Ожидают ответа «Сможешь прийти?»: " + ", ".join(pending_names))
    if declined_names:
        extra.append("Не смогут: " + ", ".join(declined_names))
    if not extra:
        extra.append("Пока нет ответов.")
    if ask_late_join:
        extra.append("")
        extra.append("Придёшь?")
    full_text = header_text + "\n\n" + "\n".join(extra)
    reply_markup = late_join_keyboard(meeting_id) if ask_late_join else None
    try:
        if header_entities:
            await bot.send_message(
                chat_id,
                full_text,
                entities=header_entities,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id,
                full_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
    except Exception as e:
        logger.warning("Не удалось отправить сводку в чат %s: %s", chat_id, e)


async def _send_organizer_summary(bot, meeting_id: str, place: str) -> None:
    """Отправляет организатору итоги после подтверждения места."""
    m = meetings.get(meeting_id)
    if not m:
        return
    await _send_meeting_summary_to_chat(bot, meeting_id, place, m.creator_user_id)


async def _send_notifications(bot, meeting_id: str, place: str) -> None:
    m = meetings.get(meeting_id)
    if not m:
        return
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    notification_text, entities = format_meeting_notification(m, slot, place)
    parse_mode = None if entities else "HTML"
    replied = [(k, p) for k, p in get_participants_for_meeting(meeting_id) if p.status == "replied"]
    for k, p in replied:
        user_id = k[1]
        sel = p.chosen_slot_ids
        if m.chosen_slot_id in sel:
            await bot.send_message(
                user_id,
                notification_text,
                entities=entities,
                parse_mode=parse_mode,
            )
        else:
            p.pending_confirm = True
            participants[k] = p
            confirm_text = (
                f"{notification_text}\n\n"
                f"Ты выбирал другие слоты. Сможешь прийти?"
            )
            await bot.send_message(
                user_id,
                confirm_text,
                entities=entities,
                parse_mode=parse_mode,
                reply_markup=can_you_come_keyboard(meeting_id),
            )
    await _send_organizer_summary(bot, meeting_id, place)
