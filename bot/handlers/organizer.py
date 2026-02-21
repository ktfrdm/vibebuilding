"""Поток организатора: storage-based state (python-telegram-bot)."""
import logging
import random
import string
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.inline import (
    can_you_come_keyboard,
    confirm_place_keyboard,
    invite_keyboard,
    skip_keyboard,
    slots_confirm_keyboard,
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


async def create_meeting_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _user_id(update)
    clear_user_state(uid)
    set_user_state(uid, "title")
    await update.message.reply_text(
        "Как назовём нашу встречу? Например: «Кофе», «Ужин в пятницу». Можно пропустить!",
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
    if step == "title":
        await _handle_title(update, uid)
    elif step == "slots":
        await _handle_slots(update, uid)
    elif step == "place":
        await _handle_place(update, context, uid)
    else:
        await msg.reply_text('Нажми «Давай соберёмся!» чтобы начать.')


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
            "Хм, не совсем понял. Напиши варианты времени попроще, например: «суббота 12:00, 15:00, 18:00»"
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
    header = "Некоторые слоты были в прошлом — убрал. Вот что получается:\n" if past else "Отлично! Вот что получается:\n"
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
    link = f"https://t.me/{username}?start=meeting_{meeting_id}"
    if query.message and query.message.chat.type in ("group", "supergroup"):
        await query.edit_message_text(
            f"Готово! Поделись ссылкой с участниками — пусть выберут удобное время:\n{link}\n\n"
            f"{title} — когда вам удобно?",
            reply_markup=invite_keyboard(meeting_id, username),
        )
    else:
        await query.edit_message_text(
            f"Готово! Поделись ссылкой с участниками — пусть выберут удобное время:\n{link}"
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
    await query.edit_message_text(
        "Где собираемся? Напиши место или нажми «Пропустить» — уточните потом в чате",
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
    await query.answer()


async def organizer_non_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    uid = _user_id(update)
    if get_user_step(uid) in ("title", "slots", "place"):
        await update.message.reply_text("Отправь, пожалуйста, текст.")


async def _send_notifications(bot, meeting_id: str, place: str) -> None:
    m = meetings.get(meeting_id)
    if not m:
        return
    slot = m.slots[m.chosen_slot_id] if m.chosen_slot_id is not None else {}
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    replied = [k for k, p in participants.items() if k[0] == meeting_id and p.status == "replied"]
    for k in replied:
        user_id = k[1]
        sel = participants[k].chosen_slot_ids
        if m.chosen_slot_id in sel:
            await bot.send_message(
                user_id,
                f"Встречаемся! {m.title} — {slot_label}. Место: {place}",
            )
        else:
            participants[k].pending_confirm = True
            await bot.send_message(
                user_id,
                f"{m.title} назначена на {slot_label}. Сможешь прийти?",
                reply_markup=can_you_come_keyboard(meeting_id),
            )
