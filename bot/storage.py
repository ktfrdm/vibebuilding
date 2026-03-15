"""Хранилище встреч и участников. При заданных SUPABASE_* использует Supabase, иначе — память."""
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


# In-memory fallback (используется когда Supabase не настроен)
_meetings: dict[str, Meeting] = {}
_participants: dict[tuple[str, int], ParticipantData] = {}
_participant_selection: dict[tuple[str, int], set[int]] = {}
_user_states: dict[int, dict[str, Any]] = {}

# Время старта создания встречи организатором (только в памяти, не в БД)
organizer_flow_start: dict[int, float] = {}


def _db():
    from bot import db as _db_module
    return _db_module


class _MeetingsStore:
    def get(self, meeting_id: str) -> Optional[Meeting]:
        if _db().is_configured():
            m = _db().get_meeting(meeting_id)
            if m is not None:
                return m
        return _meetings.get(meeting_id)

    def __setitem__(self, meeting_id: str, m: Meeting) -> None:
        if _db().is_configured():
            _db().set_meeting(m)
        _meetings[meeting_id] = m


class _ParticipantsStore:
    def get(self, key: tuple[str, int]) -> Optional[ParticipantData]:
        meeting_id, user_id = key
        if _db().is_configured():
            p = _db().get_participant(meeting_id, user_id)
            if p is not None:
                return p
        return _participants.get(key)

    def __getitem__(self, key: tuple[str, int]) -> ParticipantData:
        p = self.get(key)
        if p is None:
            raise KeyError(key)
        return p

    def __setitem__(self, key: tuple[str, int], p: ParticipantData) -> None:
        meeting_id, user_id = key
        if _db().is_configured():
            _db().set_participant(meeting_id, user_id, p)
        _participants[key] = p


class _ParticipantSelectionStore:
    def get(self, key: tuple[str, int], default: Optional[set[int]] = None) -> set[int]:
        meeting_id, user_id = key
        if _db().is_configured():
            sel = _db().get_participant_selection(meeting_id, user_id)
            return sel if sel is not None else (default or set())
        return _participant_selection.get(key, default or set())

    def __setitem__(self, key: tuple[str, int], value: set[int]) -> None:
        meeting_id, user_id = key
        if _db().is_configured():
            _db().set_participant_selection(meeting_id, user_id, value)
        _participant_selection[key] = value

    def pop(self, key: tuple[str, int], default: Optional[set[int]] = None) -> set[int]:
        meeting_id, user_id = key
        if _db().is_configured():
            _db().delete_participant_selection(meeting_id, user_id)
        return _participant_selection.pop(key, default or set())


meetings = _MeetingsStore()
participants = _ParticipantsStore()
participant_selection = _ParticipantSelectionStore()


def get_meetings_by_creator(creator_user_id: int) -> list[Meeting]:
    """Список встреч организатора (новые первые). Для сводки бери [0]."""
    if _db().is_configured():
        return _db().list_meetings_by_creator(creator_user_id)
    # В памяти — обратный порядок вставки, чтобы последняя созданная была первой
    lst = [m for m in _meetings.values() if m.creator_user_id == creator_user_id]
    return list(reversed(lst))


def get_participants_for_meeting(meeting_id: str) -> list[tuple[tuple[str, int], ParticipantData]]:
    """Список (key, ParticipantData) для встречи."""
    if _db().is_configured():
        rows = _db().list_participants_for_meeting(meeting_id)
        return [((meeting_id, uid), p) for _, uid, p in rows]
    return [(k, p) for k, p in _participants.items() if k[0] == meeting_id]


def get_user_state(user_id: int) -> Optional[dict]:
    """Текущее состояние пользователя или None."""
    if _db().is_configured():
        s = _db().get_user_state(user_id)
        if s is not None:
            return s
    return _user_states.get(user_id)


def get_user_step(user_id: int) -> str:
    """Шаг пользователя. 'idle' если нет активного flow."""
    s = get_user_state(user_id)
    return (s.get("step") or "idle") if s else "idle"


def set_user_state(user_id: int, step: str, data: Optional[dict] = None) -> None:
    """Установить состояние пользователя."""
    if _db().is_configured():
        _db().set_user_state(user_id, step, data)
    _user_states[user_id] = {"step": step, "data": data or {}}


def update_user_state(user_id: int, **kwargs: Any) -> None:
    """Обновить data в состоянии. Создаёт запись если нет."""
    s = get_user_state(user_id)
    if s is None:
        set_user_state(user_id, "idle", dict(kwargs))
        return
    data = dict(s.get("data") or {})
    data.update(kwargs)
    set_user_state(user_id, s.get("step") or "idle", data)


def clear_user_state(user_id: int) -> None:
    """Сбросить состояние пользователя."""
    if _db().is_configured():
        _db().clear_user_state(user_id)
    _user_states.pop(user_id, None)
