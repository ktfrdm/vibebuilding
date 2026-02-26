"""In-memory хранилище встреч и участников. Storage-based state (без FSM)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Слот: дата и время в человекочитаемом виде
Slot = dict  # {"date": "Суббота 15 февраля", "time": "12:00", "datetime": "2026-02-15T12:00"}


@dataclass
class Meeting:
    id: str
    title: str
    slots: list[Slot]
    status: str  # created | time_chosen
    creator_user_id: int
    chat_id: int
    chosen_slot_id: Optional[int] = None
    place: str = ""


@dataclass
class ParticipantData:
    status: str  # replied | declined | pending
    chosen_slot_ids: list[int] = field(default_factory=list)
    pending_confirm: bool = False  # ожидание «Сможешь прийти?»
    first_name: str = ""  # имя для уведомлений организатору


meetings: dict[str, Meeting] = {}
participants: dict[tuple[str, int], ParticipantData] = {}
# Временный выбор слотов до нажатия «Готово»
participant_selection: dict[tuple[str, int], set[int]] = {}

# --- Состояние организатора (storage-based, без FSM) ---
# step: idle | title | slots | slots_confirm | place
# data: для title/slots/slots_confirm — {title, slots}; для place — {meeting_id}
user_states: dict[int, dict[str, Any]] = {}


def get_user_state(user_id: int) -> Optional[dict]:
    """Текущее состояние пользователя или None."""
    return user_states.get(user_id)


def get_user_step(user_id: int) -> str:
    """Шаг пользователя. 'idle' если нет активного flow."""
    s = user_states.get(user_id)
    return (s.get("step") or "idle") if s else "idle"


def set_user_state(user_id: int, step: str, data: Optional[dict] = None) -> None:
    """Установить состояние пользователя."""
    user_states[user_id] = {"step": step, "data": data or {}}


def update_user_state(user_id: int, **kwargs: Any) -> None:
    """Обновить data в состоянии. Создаёт запись если нет."""
    if user_id not in user_states:
        user_states[user_id] = {"step": "idle", "data": {}}
    d = user_states[user_id].setdefault("data", {})
    d.update(kwargs)


def clear_user_state(user_id: int) -> None:
    """Сбросить состояние пользователя."""
    user_states.pop(user_id, None)
