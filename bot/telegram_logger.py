"""Отправка событий бота в Telegram-группу логов (Vibe logs)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bot.logs_destination import get_logs_chat_id

logger = logging.getLogger(__name__)

# Разделитель для читаемости (как в примерах логов).
_SEP = "━━━━━━━━━━━━━━━━━━━━━━━━"


def _user_label(username: str | None, first_name: str | None, user_id: int) -> str:
    """Идентификация пользователя для логов: @username или имя или id."""
    if username:
        return f"@{username}"
    if first_name and first_name.strip():
        return first_name.strip()
    return f"id:{user_id}"


def _ts() -> str:
    """Время события для лога (UTC)."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _format_duration(seconds: float) -> str:
    """Форматирование длительности: минуты и секунды."""
    if seconds is None or seconds < 0:
        return "—"
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m > 0:
        return f"{m} мин {s} сек"
    return f"{s} сек"


async def send_log_event(bot: Any, event: str, **payload: Any) -> None:
    """
    Отправляет одно событие в группу логов. Если chat_id не настроен — не отправляет.
    event: organizer_start | organizer_meeting_created | organizer_notifications_sent |
           participant_opened | participant_replied | participant_declined | error
    """
    chat_id = get_logs_chat_id()
    if chat_id is None:
        logger.debug("Лог не отправлен: chat_id для Vibe logs не настроен (VIBE_LOGS_CHAT_ID или /logs в группе).")
        return
    try:
        text = _build_log_text(event, **payload)
        if not text:
            return
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.warning("Не удалось отправить лог в группу: %s", e)


def _build_log_text(event: str, **payload: Any) -> str:
    """Формирует текст сообщения для лога по типу события и payload (формат как в лучших практиках)."""
    t = _ts()
    if event == "organizer_start":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        uid = payload.get("user_id", "")
        return (
            f"📅 Vibe · Начало создания встречи\n{_SEP}\n"
            f"👤 Организатор: {label}\n"
            f"🆔 User ID: {uid}\n"
            f"🕒 {t}\n{_SEP}"
        )
    if event == "organizer_meeting_created":
        title = payload.get("title", "—")
        slots_count = payload.get("slots_count", 0)
        return (
            f"📅 Vibe · Встреча создана\n{_SEP}\n"
            f"📋 Встреча: «{title}»\n"
            f"📊 Слотов: {slots_count}\n"
            f"🕒 {t}\n{_SEP}"
        )
    if event == "organizer_notifications_sent":
        title = payload.get("title", "—")
        participants_count = payload.get("participants_count", 0)
        duration_sec = payload.get("duration_sec")
        duration_str = _format_duration(duration_sec) if duration_sec is not None else "—"
        return (
            f"📅 Vibe · Рассылка участникам\n{_SEP}\n"
            f"📋 Встреча: «{title}»\n"
            f"👥 Участников: {participants_count}\n"
            f"⏱️ Длительность: {duration_str}\n"
            f"🕒 {t}\n{_SEP}"
        )
    if event == "participant_opened":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        title = payload.get("title", "—")
        return (
            f"📅 Vibe · Участник открыл приглашение\n{_SEP}\n"
            f"👤 Участник: {label}\n"
            f"📋 Встреча: «{title}»\n"
            f"🕒 {t}\n{_SEP}"
        )
    if event == "participant_replied":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        title = payload.get("title", "—")
        slots_count = payload.get("chosen_slots_count", 0)
        return (
            f"📅 Vibe · Участник ответил\n{_SEP}\n"
            f"👤 Участник: {label}\n"
            f"📋 Встреча: «{title}»\n"
            f"📊 Выбрано слотов: {slots_count}\n"
            f"🕒 {t}\n{_SEP}"
        )
    if event == "participant_declined":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        title = payload.get("title", "—")
        return (
            f"📅 Vibe · Участник отказался\n{_SEP}\n"
            f"👤 Участник: {label}\n"
            f"📋 Встреча: «{title}»\n"
            f"🕒 {t}\n{_SEP}"
        )
    if event == "error":
        where = payload.get("where", "сервис")
        where_ru = "Пользователь" if where == "user" else "Сервис"
        err_type = payload.get("error_type", "Error")
        err_msg = (payload.get("error_message") or str(payload.get("exception", "")))[:200]
        lines = [
            f"⚠️ Vibe · Ошибка\n{_SEP}",
            f"📌 Контекст: {where_ru}",
        ]
        if where == "user" and (payload.get("user_id") or payload.get("username") or payload.get("first_name")):
            label = _user_label(
                payload.get("username"),
                payload.get("first_name"),
                payload.get("user_id", 0),
            )
            lines.append(f"👤 {label} (🆔 {payload.get('user_id', '')})")
        step = payload.get("step")
        if step:
            lines.append(f"📋 Шаг: {step}")
        user_input = payload.get("user_input")
        if user_input is not None and str(user_input).strip():
            inp = str(user_input).strip()[:400]
            if len(str(user_input).strip()) > 400:
                inp += "…"
            lines.append(f"✏️ Ввод: {inp}")
        lines.append(f"❌ {err_type}: {err_msg}")
        lines.append(f"🕒 {t}\n{_SEP}")
        return "\n".join(lines)
    return ""
