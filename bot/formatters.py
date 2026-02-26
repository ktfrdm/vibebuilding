"""Форматирование текста для Telegram (теги, HTML)."""
import html


def participant_tag(user_id: int, first_name: str) -> str:
    """Тег участника для Telegram (ссылка на профиль)."""
    name = (first_name or "Участник").strip() or "Участник"
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'
