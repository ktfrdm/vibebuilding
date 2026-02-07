"""Вспомогательные функции."""
from typing import Optional


def format_user_name(user) -> str:
    """Форматирует имя пользователя."""
    name_parts = []
    if user.first_name:
        name_parts.append(user.first_name)
    if user.last_name:
        name_parts.append(user.last_name)
    return " ".join(name_parts) if name_parts else user.username or "Пользователь"


def validate_input(text: str, min_length: int = 1, max_length: int = 1000) -> Optional[str]:
    """
    Валидирует ввод пользователя.
    
    Args:
        text: Текст для валидации
        min_length: Минимальная длина
        max_length: Максимальная длина
        
    Returns:
        Ошибка валидации или None если все ок
    """
    if not text:
        return "Текст не может быть пустым"
    if len(text) < min_length:
        return f"Текст слишком короткий (минимум {min_length} символов)"
    if len(text) > max_length:
        return f"Текст слишком длинный (максимум {max_length} символов)"
    return None
