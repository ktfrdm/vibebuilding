"""Inline клавиатуры."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню с inline-кнопками."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Кнопка 1", callback_data="button_1"),
            InlineKeyboardButton(text="Кнопка 2", callback_data="button_2"),
        ],
        [
            InlineKeyboardButton(text="Помощь", callback_data="help"),
        ]
    ])
    return keyboard
