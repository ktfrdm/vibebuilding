"""Inline-клавиатуры и Reply-клавиатуры (python-telegram-bot)."""
from __future__ import annotations

from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.storage import Slot


def start_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура: видимая кнопка «Давай соберёмся!» под полем ввода."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Давай соберёмся!")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip")],
    ])


def slots_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да!", callback_data="slots_ok")],
        [InlineKeyboardButton(text="Изменить", callback_data="slots_edit")],
    ])


def participant_slots_keyboard(slots: list[Slot], meeting_id: str, chosen_ids: set[int]) -> InlineKeyboardMarkup:
    """Кнопки слотов: toggle удобно/не удобно."""
    rows = []
    for i, s in enumerate(slots):
        label = f"{s.get('date', '')} {s.get('time', '')}".strip()
        mark = "✓ " if i in chosen_ids else ""
        rows.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"slot_toggle:{meeting_id}:{i}"
        )])
    rows.append([InlineKeyboardButton(text="Увы, не смогу", callback_data=f"decline:{meeting_id}")])
    rows.append([InlineKeyboardButton(text="Готово", callback_data=f"done:{meeting_id}")])
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
            text=f"Встречаемся! {label} ({ok}/{total})",
            callback_data=f"choose_slot:{meeting_id}:{slot_idx}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_place_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="place_skip")],
    ])


def can_you_come_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, приду!", callback_data=f"confirm_yes:{meeting_id}")],
        [InlineKeyboardButton(text="Увы, не смогу", callback_data=f"confirm_no:{meeting_id}")],
    ])


def late_join_keyboard(meeting_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для нового пользователя, перешедшего по ссылке после назначения встречи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, приду!", callback_data=f"late_join_yes:{meeting_id}")],
        [InlineKeyboardButton(text="Увы, не смогу", callback_data=f"late_join_no:{meeting_id}")],
    ])


def invite_keyboard(meeting_id: str, bot_username: str) -> InlineKeyboardMarkup:
    link = f"https://t.me/{bot_username}?start=meeting_{meeting_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ответить на приглашение", url=link)],
    ])
