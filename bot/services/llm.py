"""Парсинг опций для встречи через OpenAI. Только LLM — в коде бота парсинга дат нет."""
import json
from datetime import datetime


def is_slot_in_past(slot: dict) -> bool:
    """Проверяет, относится ли слот к прошлому. datetime в формате YYYY-MM-DDThh:mm."""
    dt_str = slot.get("datetime") if isinstance(slot, dict) else None
    if not dt_str:
        return False  # без datetime не проверяем
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None) < datetime.now()
    except (ValueError, TypeError):
        return False


def filter_past_slots(slots: list) -> tuple[list, list]:
    """Удаляет слоты в прошлом. Возвращает (валидные_слоты, удалённые_в_прошлом)."""
    future, past = [], []
    for s in slots:
        sl = s if isinstance(s, dict) else {"date": str(s), "time": "", "datetime": ""}
        if is_slot_in_past(sl):
            past.append(sl)
        else:
            future.append(sl)
    return future, past

from openai import OpenAI

from bot.config import OPENAI_API_KEY

SLOTS_SYSTEM = """Ты парсишь опции для встречи. Организатор пишет, какие варианты времени предложить участникам.
Текущая дата: {today}.

Правила:
1. **Разделители вариантов** — слоты могут быть перечислены:
   - через запятую, «или», «и»;
   - с новой строки (перенос строки = разделитель; в одной строке может быть несколько времени через запятую/пробел, тогда общая дата/день из строки относится ко всем).
   Пример: строка «Понедельник 13-35, 14-35, 16-35» → три слота в понедельник: 13:35, 14:35, 16:35.
2. **Время с дефисом** — пользователи часто пишут время через дефис вместо двоеточия: 13-35 = 13:35, 16-35 = 16:35. Интерпретируй так же.
3. **Относительные даты**: «завтра» = следующий день от сегодня; «послезавтра» = через 2 дня. Время без указания — по умолчанию 12:00.
4. **День недели** (понедельник, вторник, … воскресенье): брать БЛИЖАЙШИЙ такой день от текущей даты в будущем.
5. **Дата вида ДД.ММ** или **ДД.ММ в HH-MM**: один слот в указанную дату и время (год — текущий, если не указан).
6. **Все слоты в будущем.** Нельзя назначить встречу в прошлом. Если дата в прошлом — {{"ok": false, "error": "Дата в прошлом."}}.
7. **Порядок слотов** — после распознавания упорядочь слоты в хронологическом порядке: от ближайшего к дальнему (по полю datetime). Первый элемент массива slots — самый ранний вариант.

Формат ответа: JSON. Каждый слот: {{"date": "Суббота 15 февраля", "time": "12:00", "datetime": "2026-02-15T12:00"}}. Поле datetime обязательно в формате YYYY-MM-DDThh:mm. Массив slots — отсортирован по возрастанию datetime.
Верни: {{"ok": true, "slots": [...]}} или {{"ok": false, "error": "причина"}}.

Примеры:
- "завтра 12:00" -> 1 слот
- "завтра в 12 или послезавтра в 15" -> 2 слота
- "суббота 12:00, 15:00, 18:00" -> 3 слота в ближайшую субботу
- "Понедельник 13-35, 14-35, 16-35" -> 3 слота в понедельник (13:35, 14:35, 16:35)
- "03.03 в 16-35" -> один слот 3 марта 16:35
- Текст из нескольких строк: первая строка «суббота 12:00, 15:00, 18:00», вторая «Понедельник 13-35, 14-35», третья «03.03 в 16-35» -> обрабатывай каждую строку с её контекстом даты/дня, все слоты в один массив.
"""


def _call_llm(system: str, user: str) -> dict:
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OpenAI API key not configured"}
    client = OpenAI(api_key=OPENAI_API_KEY)
    today = datetime.now().strftime("%d.%m.%Y, %A")
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system.format(today=today)},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        text = r.choices[0].message.content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(l for l in lines if not l.startswith("```"))
        return json.loads(text)
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _parse_datetime_for_sort(slot: dict) -> datetime | None:
    """Извлекает datetime слота для сортировки. Возвращает None если нет или невалидно."""
    dt_str = slot.get("datetime") if isinstance(slot, dict) else None
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def parse_options(text: str) -> dict:
    """
    Парсит опции для встречи через LLM.
    Возвращает {ok: true, slots: [...]} или {ok: false, error: "..."}.
    Слоты в формате [{date, time, datetime}, ...], отсортированы от ближайшего к дальнему.
    """
    user_msg = f"Организатор написал: {text}"
    result = _call_llm(SLOTS_SYSTEM, user_msg)
    if result.get("ok") and result.get("slots"):
        slots = result["slots"]
        # Упорядочиваем по datetime на случай если LLM не отсортировал
        with_dt = [(_parse_datetime_for_sort(s), s) for s in slots]
        with_dt.sort(key=lambda x: (x[0] is None, x[0] or datetime.max))
        result["slots"] = [s for _, s in with_dt]
    return result
