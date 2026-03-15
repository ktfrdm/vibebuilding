"""
Слой доступа к Supabase. Используется только при заданных SUPABASE_URL и SUPABASE_SERVICE_KEY.
Иначе все функции — no-op / возвращают None или пустые списки (storage продолжает использовать память).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from bot.config import SUPABASE_SERVICE_KEY, SUPABASE_URL
from bot.storage import Meeting, ParticipantData

logger = logging.getLogger(__name__)

_client: Any = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        return _client
    except Exception as e:
        logger.warning("Supabase client init failed: %s", e)
        return None


def is_configured() -> bool:
    """True, если заданы URL и ключ и клиент успешно инициализирован."""
    return _get_client() is not None


# --- Meetings ---

def get_meeting(meeting_id: str) -> Optional[Meeting]:
    """Встреча по id или None."""
    client = _get_client()
    if not client:
        return None
    try:
        r = client.table("meetings").select("*").eq("id", meeting_id).maybe_single().execute()
        row = r.data if hasattr(r, "data") else None
        if not row:
            return None
        return _row_to_meeting(row)
    except Exception as e:
        logger.warning("db get_meeting %s: %s", meeting_id, e)
        return None


def set_meeting(m: Meeting) -> None:
    """Создать или обновить встречу (upsert)."""
    client = _get_client()
    if not client:
        return
    try:
        row = {
            "id": m.id,
            "title": m.title,
            "slots": m.slots,
            "status": m.status,
            "creator_user_id": m.creator_user_id,
            "chat_id": m.chat_id,
            "chosen_slot_id": m.chosen_slot_id,
            "place": m.place or "",
        }
        client.table("meetings").upsert(row).execute()
    except Exception as e:
        logger.warning("db set_meeting %s: %s", m.id, e)


def list_meetings_by_creator(creator_user_id: int) -> list[Meeting]:
    """Список встреч организатора (по creator_user_id)."""
    client = _get_client()
    if not client:
        return []
    try:
        r = client.table("meetings").select("*").eq("creator_user_id", creator_user_id).order("created_at", desc=True).execute()
        rows = r.data if hasattr(r, "data") else []
        return [_row_to_meeting(row) for row in rows]
    except Exception as e:
        logger.warning("db list_meetings_by_creator: %s", e)
        return []


def _row_to_meeting(row: dict) -> Meeting:
    return Meeting(
        id=row["id"],
        title=row.get("title") or "",
        slots=row.get("slots") or [],
        status=row.get("status") or "created",
        creator_user_id=int(row["creator_user_id"]),
        chat_id=int(row["chat_id"]),
        chosen_slot_id=row.get("chosen_slot_id"),
        place=row.get("place") or "",
    )


# --- Participants ---

def get_participant(meeting_id: str, user_id: int) -> Optional[ParticipantData]:
    """Данные участника по встрече и user_id."""
    client = _get_client()
    if not client:
        return None
    try:
        r = (
            client.table("participants")
            .select("*")
            .eq("meeting_id", meeting_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        row = r.data if hasattr(r, "data") else None
        if not row:
            return None
        return _row_to_participant(row)
    except Exception as e:
        logger.warning("db get_participant %s %s: %s", meeting_id, user_id, e)
        return None


def set_participant(meeting_id: str, user_id: int, p: ParticipantData) -> None:
    """Создать или обновить участника (upsert)."""
    client = _get_client()
    if not client:
        return
    try:
        row = {
            "meeting_id": meeting_id,
            "user_id": user_id,
            "status": p.status,
            "chosen_slot_ids": p.chosen_slot_ids,
            "pending_confirm": p.pending_confirm,
            "first_name": p.first_name or "",
        }
        client.table("participants").upsert(row).execute()
    except Exception as e:
        logger.warning("db set_participant %s %s: %s", meeting_id, user_id, e)


def list_participants_for_meeting(meeting_id: str) -> list[tuple[str, int, ParticipantData]]:
    """Список (meeting_id, user_id, ParticipantData) для встречи."""
    client = _get_client()
    if not client:
        return []
    try:
        r = client.table("participants").select("*").eq("meeting_id", meeting_id).execute()
        rows = r.data if hasattr(r, "data") else []
        return [(meeting_id, int(row["user_id"]), _row_to_participant(row)) for row in rows]
    except Exception as e:
        logger.warning("db list_participants_for_meeting %s: %s", meeting_id, e)
        return []


def _row_to_participant(row: dict) -> ParticipantData:
    ids = row.get("chosen_slot_ids")
    if not isinstance(ids, list):
        ids = []
    return ParticipantData(
        status=row.get("status") or "pending",
        chosen_slot_ids=[int(x) for x in ids],
        pending_confirm=bool(row.get("pending_confirm")),
        first_name=row.get("first_name") or "",
    )


# --- Participant selection (draft) ---

def get_participant_selection(meeting_id: str, user_id: int) -> set[int]:
    """Текущий черновик выбора слотов (индексы)."""
    client = _get_client()
    if not client:
        return set()
    try:
        r = (
            client.table("participant_selection")
            .select("slot_indices")
            .eq("meeting_id", meeting_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        row = r.data if hasattr(r, "data") else None
        if not row:
            return set()
        indices = row.get("slot_indices") or []
        return set(int(x) for x in indices) if isinstance(indices, list) else set()
    except Exception as e:
        logger.warning("db get_participant_selection %s %s: %s", meeting_id, user_id, e)
        return set()


def set_participant_selection(meeting_id: str, user_id: int, slot_indices: set[int]) -> None:
    """Сохранить черновик выбора слотов."""
    client = _get_client()
    if not client:
        return
    try:
        row = {
            "meeting_id": meeting_id,
            "user_id": user_id,
            "slot_indices": list(slot_indices),
        }
        client.table("participant_selection").upsert(row).execute()
    except Exception as e:
        logger.warning("db set_participant_selection %s %s: %s", meeting_id, user_id, e)


def delete_participant_selection(meeting_id: str, user_id: int) -> None:
    """Удалить черновик (после «Готово»)."""
    client = _get_client()
    if not client:
        return
    try:
        client.table("participant_selection").delete().eq("meeting_id", meeting_id).eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning("db delete_participant_selection %s %s: %s", meeting_id, user_id, e)


# --- User states (organizer flow) ---

def get_user_state(user_id: int) -> Optional[dict[str, Any]]:
    """Состояние организатора: { step, data } или None."""
    client = _get_client()
    if not client:
        return None
    try:
        r = client.table("user_states").select("*").eq("user_id", user_id).maybe_single().execute()
        row = r.data if hasattr(r, "data") else None
        if not row:
            return None
        return {"step": row.get("step") or "idle", "data": row.get("data") or {}}
    except Exception as e:
        logger.warning("db get_user_state %s: %s", user_id, e)
        return None


def set_user_state(user_id: int, step: str, data: Optional[dict] = None) -> None:
    """Записать состояние организатора (upsert)."""
    client = _get_client()
    if not client:
        return
    try:
        row = {"user_id": user_id, "step": step, "data": data or {}}
        client.table("user_states").upsert(row).execute()
    except Exception as e:
        logger.warning("db set_user_state %s: %s", user_id, e)


def clear_user_state(user_id: int) -> None:
    """Удалить состояние организатора."""
    client = _get_client()
    if not client:
        return
    try:
        client.table("user_states").delete().eq("user_id", user_id).execute()
    except Exception as e:
        logger.warning("db clear_user_state %s: %s", user_id, e)
