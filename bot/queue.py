"""Очередь запросов: последовательная обработка обновлений по пользователю.

Обеспечивает, что действия одного пользователя обрабатываются строго по порядку.
Разные пользователи обрабатываются параллельно (в пределах max_concurrent_updates).
"""
import asyncio
import logging

from telegram import Update
from telegram.ext import BaseUpdateProcessor

logger = logging.getLogger(__name__)


def _user_key(update: object) -> int:
    """Ключ для сериализации: user_id или chat_id."""
    if not isinstance(update, Update):
        return id(update)
    user = update.effective_user
    if user:
        return user.id
    chat = update.effective_chat
    if chat:
        return chat.id
    return id(update)  # fallback


class PerUserUpdateProcessor(BaseUpdateProcessor):
    """Обрабатывает обновления последовательно в рамках одного пользователя."""

    def __init__(self, max_concurrent_updates: int = 64):
        super().__init__(max_concurrent_updates)
        self._locks: dict[int, asyncio.Lock] = {}

    def _get_lock(self, key: int) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def do_process_update(self, update: object, coroutine) -> None:
        key = _user_key(update)
        lock = self._get_lock(key)
        async with lock:
            await coroutine

    async def initialize(self) -> None:
        logger.info("PerUserUpdateProcessor: очередь по пользователям включена")

    async def shutdown(self) -> None:
        self._locks.clear()
        logger.info("PerUserUpdateProcessor: shutdown")
