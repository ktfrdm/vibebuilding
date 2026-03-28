"""Inline-клавиатуры и Reply-клавиатуры (python-telegram-bot)."""
from __future__ import annotations

from urllib.parse import quote

from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.storage import Slot


def start_inline_keyboard() -> InlineKeyboardMarkup:
    """Главное меню: создать встречу и статус (после того как встреча есть)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤝 Давай соберёмся!", callback_data="start_meeting")],
        [InlineKeyboardButton(text="📋 Статус", callback_data="main_svodka")],
    ])


def start_inline_keyboard_first() -> InlineKeyboardMarkup:
    """Только при первом запуске: одна кнопка «Давай соберёмся!». Статус — через меню бота (/svodka)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤝 Давай соберёмся!", callback_data="start_meeting")],
    ])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip")],
    ])


def slots_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, подходит", callback_data="slots_ok")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="slots_edit")],
    ])


def participant_slots_keyboard(slots: list[Slot], meeting_id: str, chosen_ids: set[int]) -> InlineKeyboardMarkup:
    """Кнопки слотов: наглядно отмечены выбранные (✅) и невыбранные (☐)."""
    rows = []
    for i, s in enumerate(slots):
        label = f"{s.get('date', '')} {s.get('time', '')}".strip()
        if not label:
            label = f"Слот {i + 1}"
        if i in chosen_ids:
            text = f"✅ {label}"
        else:
            text = f"☐ {label}"
        rows.append([InlineKeyboardButton(
            text=text,
            callback_data=f"slot_toggle:{meeting_id}:{i}"
        )])
    rows.append([InlineKeyboardButton(text="😔 Увы, не смогу", callback_data=f"decline:{meeting_id}")])
    # Голубая кнопка «Готово» (style=primary в Bot API 9.4+)
    rows.append([InlineKeyboardButton(
        text="📤 Готово — отправить ответ",
        callback_data=f"done:{meeting_id}",
        api_kwargs={"style": "primary"},
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def organizer_choose_slot_keyboard(
    slots: list[Slot], meeting_id: str, counts: list[tuple[int, int]],
    original_indices: Optional[list[int]] = None,
) -> InlineKeyboardMarkup:
    """Кнопки выбора итогового слота. counts: (удобно, всего_ответивших).
    original_indices: при упорядоченных слотах — исходные индексы в m.slots для callback.
    """
    rows = []
    for i, s in enumerate(slots):
        ok, total = counts[i] if i < len(counts) else (0, 0)
        label = f"{s.get('date', '')} {s.get('time', '')}".strip()
        slot_idx = original_indices[i] if original_indices and i < len(original_indices) else i
        rows.append([InlineKeyboardButton(
            text=f"🗓 Встречаемся! {label} ({ok}/{total})",
            callback_data=f"choose_slot:{meeting_id}:{slot_idx}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_place_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить место", callback_data="place_skip")],
    ])


def can_you_come_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Да, приду!", callback_data=f"confirm_yes:{meeting_id}")],
        [InlineKeyboardButton(text="😔 Увы, не смогу", callback_data=f"confirm_no:{meeting_id}")],
    ])


def late_join_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для нового пользователя, перешедшего по ссылке после назначения встречи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 Да, приду!", callback_data=f"late_join_yes:{meeting_id}")],
        [InlineKeyboardButton(text="😔 Увы, не смогу", callback_data=f"late_join_no:{meeting_id}")],
    ])


def meeting_deeplink(bot_username: str, meeting_id: str) -> str:
    """Ссылка start=meeting_… для участника (открывает бота сразу во встрече)."""
    mid = meeting_id.replace("m_", "") if meeting_id.startswith("m_") else meeting_id
    return f"https://t.me/{bot_username}?start=meeting_{mid}"


def invite_share_telegram_url(bot_username: str, meeting_id: str, title: str = "") -> str:
    """t.me/share/url — нативный выбор чата/контактов для рассылки приглашения."""
    link = meeting_deeplink(bot_username, meeting_id)
    share_text = f"Приглашение на встречу «{title}»" if title else "Приглашение на встречу"
    return f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"


def invite_keyboard_for_organizer(bot_username: str, meeting_id: str, title: str = "") -> InlineKeyboardMarkup:
    """Клавиатура для организатора: только переслать (без «ответить»)."""
    share_url = invite_share_telegram_url(bot_username, meeting_id, title)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Переслать приглашение", url=share_url)],
    ])


def invite_keyboard_private_organizer(meeting_id: str, bot_username: str, title: str = "") -> InlineKeyboardMarkup:
    """Личка после создания встречи: переслать через Telegram + та же deep link для проверки."""
    link = meeting_deeplink(bot_username, meeting_id)
    share_url = invite_share_telegram_url(bot_username, meeting_id, title)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Переслать приглашение", url=share_url)],
        [InlineKeyboardButton(text="📅 Ответить на приглашение", url=link)],
    ])


def invite_keyboard(meeting_id: str, bot_username: str, title: str = "") -> InlineKeyboardMarkup:
    """Одна кнопка «Ответить» — при пересылке участник нажимает и выбирает слоты."""
    link = meeting_deeplink(bot_username, meeting_id)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Ответить на приглашение", url=link)],
    ])


def organizer_notification_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    """Две кнопки под уведомлениями: просмотр ответов и выбор времени."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Статус", callback_data=f"show_svodka:{meeting_id}"),
            InlineKeyboardButton(text="⏰ Выбрать время", callback_data=f"choose_time:{meeting_id}"),
        ],
    ])


def organizer_summary_view_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    """Одна кнопка под сводкой «только просмотр»: переход к выбору времени."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Выбрать время", callback_data=f"choose_time:{meeting_id}")],
    ])
