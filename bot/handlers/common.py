"""Общие обработчики сообщений."""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

router = Router()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    help_text = """
📖 Доступные команды:

/start - Начать работу с ботом
/help - Показать это сообщение

Для получения дополнительной информации обратитесь к документации.
    """
    await message.answer(help_text.strip())


@router.message(F.text)
async def echo_message(message: Message):
    """Эхо-обработчик для текстовых сообщений."""
    await message.answer(f"Вы написали: {message.text}")
