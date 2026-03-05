"""Чтение/запись chat_id группы для логов (команда /logs)."""
from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"
_LOGS_CHAT_ID_FILE = _DATA_DIR / "logs_chat_id.json"


def get_logs_chat_id() -> int | None:
    """Возвращает chat_id группы для логов или None, если не настроено."""
    if not _LOGS_CHAT_ID_FILE.exists():
        return None
    try:
        data = json.loads(_LOGS_CHAT_ID_FILE.read_text(encoding="utf-8"))
        return data.get("chat_id")
    except (json.JSONDecodeError, OSError):
        return None


def set_logs_chat_id(chat_id: int) -> None:
    """Сохраняет chat_id группы для логов."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _LOGS_CHAT_ID_FILE.write_text(
        json.dumps({"chat_id": chat_id}, ensure_ascii=False),
        encoding="utf-8",
    )
