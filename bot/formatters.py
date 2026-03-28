"""Форматирование текста для Telegram (теги, HTML, date_time entity)."""
from __future__ import annotations

import html
from datetime import datetime
from typing import TYPE_CHECKING, Any

from telegram import MessageEntity

if TYPE_CHECKING:
    from bot.storage import Meeting


def participant_tag(user_id: int, first_name: str) -> str:
    """Тег участника для Telegram (ссылка на профиль)."""
    name = (first_name or "Участник").strip() or "Участник"
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'


def slot_unix_time(slot: dict[str, Any]) -> int | None:
    """Возвращает Unix timestamp слота из поля datetime (ISO) или None."""
    dt_str = slot.get("datetime") if isinstance(slot, dict) else None
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return None


def utf16_len(s: str) -> int:
    """Длина строки в UTF-16 code units (для offset/length в MessageEntity)."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


# Формат отображения даты/времени в Telegram (день недели + короткая дата + короткое время)
DATE_TIME_FORMAT = "wDt"


def format_meeting_notification(
    m: "Meeting", slot: dict[str, Any], place: str
) -> tuple[str, list[MessageEntity] | None]:
    """
    Текст уведомления о встрече и опционально entities для кликабельного времени (API 9.5).
    Возвращает (text, entities). Если у слота есть datetime — entities содержит date_time.
    """
    title_esc = html.escape((m.title or "Встреча").strip())
    if title_esc == "Встреча":
        title_part = ""
    else:
        title_part = f" «{title_esc}»"
    place_esc = html.escape(place or "уточните в чате")
    slot_label = f"{slot.get('date', '')} {slot.get('time', '')}".strip()
    slot_esc = html.escape(slot_label)

    # Один эмодзи на сообщение — акцент на «встречаемся».
    text = (
        f"🗓 Встречаемся!{title_part}\n\n"
        f"Время: {slot_esc}\n"
        f"Место: {place_esc}"
    )
    unix = slot_unix_time(slot)
    if unix is None or not slot_label:
        return (text, None)
    prefix = f"🗓 Встречаемся!{title_part}\n\nВремя: "
    offset = utf16_len(prefix)
    length = utf16_len(slot_label)
    entity = MessageEntity(
        type="date_time",
        offset=offset,
        length=length,
        api_kwargs={"unix_time": unix, "date_time_format": DATE_TIME_FORMAT},
    )
    return (text, [entity])


def shift_entities(
    entities: list[MessageEntity], delta: int
) -> list[MessageEntity]:
    """Сдвигает offset всех entities на delta (для вставки префикса перед текстом)."""
    result = []
    for e in entities:
        api_kwargs = dict(getattr(e, "api_kwargs", None) or {})
        result.append(
            MessageEntity(
                type=e.type,
                offset=e.offset + delta,
                length=e.length,
                url=e.url,
                user=e.user,
                language=e.language,
                custom_emoji_id=e.custom_emoji_id,
                api_kwargs=api_kwargs or None,
            )
        )
    return result
