"""Отправка событий бота в Telegram-группу логов (Vibe logs)."""
from __future__ import annotations

import logging
from typing import Any

from bot.logs_destination import get_logs_chat_id

logger = logging.getLogger(__name__)


def _user_label(username: str | None, first_name: str | None, user_id: int) -> str:
    """Идентификация пользователя для логов: @username или имя или id."""
    if username:
        return f"@{username}"
    if first_name and first_name.strip():
        return first_name.strip()
    return f"id:{user_id}"


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
    """Формирует текст сообщения для лога по типу события и payload."""
    if event == "organizer_start":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        return f"[Vibe] Организатор | Начало создания встречи | {label} (id: {payload.get('user_id', '')})"
    if event == "organizer_meeting_created":
        title = payload.get("title", "—")
        slots_count = payload.get("slots_count", 0)
        return f"[Vibe] Организатор | Встреча создана | «{title}», слотов: {slots_count}"
    if event == "organizer_notifications_sent":
        title = payload.get("title", "—")
        participants_count = payload.get("participants_count", 0)
        duration_sec = payload.get("duration_sec")
        duration_str = _format_duration(duration_sec) if duration_sec is not None else "—"
        return f"[Vibe] Организатор | Рассылка участникам | «{title}», участников: {participants_count}, длительность: {duration_str}"
    if event == "participant_opened":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        title = payload.get("title", "—")
        return f"[Vibe] Участник | Открыл приглашение | {label}, встреча «{title}»"
    if event == "participant_replied":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        title = payload.get("title", "—")
        slots_count = payload.get("chosen_slots_count", 0)
        return f"[Vibe] Участник | Ответил | {label}, встреча «{title}», слотов: {slots_count}"
    if event == "participant_declined":
        label = _user_label(
            payload.get("username"),
            payload.get("first_name"),
            payload.get("user_id", 0),
        )
        title = payload.get("title", "—")
        return f"[Vibe] Участник | Отказался | {label}, встреча «{title}»"
    if event == "error":
        # Немедленный лог при ошибке: контекст (пользователь/сервис), кто, что упало.
        where = payload.get("where", "сервис")  # "user" -> "Пользователь", "service" -> "Сервис"
        where_ru = "Пользователь" if where == "user" else "Сервис"
        err_type = payload.get("error_type", "Error")
        err_msg = (payload.get("error_message") or str(payload.get("exception", "")))[:200]
        user_part = ""
        if where == "user" and (payload.get("user_id") or payload.get("username") or payload.get("first_name")):
            label = _user_label(
                payload.get("username"),
                payload.get("first_name"),
                payload.get("user_id", 0),
            )
            user_part = f"{label} (id: {payload.get('user_id', '')}). "
        step = payload.get("step")
        step_part = f" Шаг: {step}." if step else ""
        return f"[Vibe] ⚠ Ошибка | {where_ru} | {user_part}{err_type}: {err_msg}.{step_part}"
    return ""
