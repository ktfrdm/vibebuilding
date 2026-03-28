"""Тип чата Telegram и подсказки для флоу организатора.

Продуктовый выбор: целевой сценарий для группы — полное создание встречи в групповом чате (B1b),
с учётом групповой приватности бота. Доработка флоу в личке — приоритет следующих итераций.
См. docs/product-description/03. Scenarios/ORGANIZER_FLOW_IMPLEMENTATION_STATUS.md
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from telegram import Chat


# Текст шага «название» (без подсказки про группу)
ORGANIZER_TITLE_PROMPT = (
    "💬 Как назовём нашу встречу? Например: «Кофе», «Ужин в пятницу». Можно пропустить!"
)

# Подсказка при вводе текста организатором в group/supergroup
GROUP_ORGANIZER_REPLY_HINT = (
    "\n\nВ группе отвечай на это сообщение бота своим текстом — "
    "при включённой у бота «групповой приватности» он иначе не увидит обычные сообщения в чате."
)


def is_group_like_chat(chat: Optional["Chat"]) -> bool:
    """True для группы и супергруппы."""
    if not chat:
        return False
    return chat.type in ("group", "supergroup")


def is_private_chat(chat: Optional["Chat"]) -> bool:
    """True для личного диалога с ботом."""
    if not chat:
        return False
    return chat.type == "private"


def append_group_organizer_hint(text: str, chat: Optional["Chat"]) -> str:
    """Добавляет подсказку про ответ на сообщение бота, если чат групповой."""
    if is_group_like_chat(chat):
        return text + GROUP_ORGANIZER_REPLY_HINT
    return text
