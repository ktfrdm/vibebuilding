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
1. **Несколько вариантов** — если организатор перечисляет через «или», запятую или «и» — каждый вариант = отдельный слот. Пример: «завтра в 12 или послезавтра в 15» -> 2 слота.
2. **Относительные даты**: «завтра» = следующий день от сегодня; «послезавтра» = через 2 дня. Время без указания — по умолчанию 12:00.
3. **День недели** (понедельник, вторник, среда, четверг, пятница, суббота, воскресенье): брать БЛИЖАЙШИЙ такой день от текущей даты в будущем. «Вторник» при сегодня понедельник -> завтрашний вторник; если сегодня вторник -> следующий вторник (через неделю).
4. **Все слоты в будущем.** Нельзя назначить встречу в прошлом. Если дата в прошлом — {{"ok": false, "error": "Дата в прошлом."}}.

Формат ответа: JSON. Каждый слот: {{"date": "Суббота 15 февраля", "time": "12:00", "datetime": "2026-02-15T12:00"}}. Поле datetime обязательно в формате YYYY-MM-DDThh:mm.
Верни: {{"ok": true, "slots": [...]}} или {{"ok": false, "error": "причина"}}.

Примеры:
- "завтра 12:00" -> 1 слот на завтра 12:00
- "послезавтра в 15:00" -> 1 слот
- "завтра в 12 или послезавтра в 15" -> 2 слота
- "вторник 10:00" -> ближайший вторник 10:00
- "суббота 12:00, 15:00, 18:00" -> 3 слота в ближайшую субботу
- "25 февраля вечером" -> слот(ы) вечером 25 февраля
- "понедельник или среда" -> 2 слота (ближайший понедельник и ближайшая среда, время по умолчанию 12:00)
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


def parse_options(text: str) -> dict:
    """
    Парсит опции для встречи через LLM.
    Возвращает {ok: true, slots: [...]} или {ok: false, error: "..."}.
    Слоты в формате [{date, time, datetime}, ...].
    """
    user_msg = f"Организатор написал: {text}"
    return _call_llm(SLOTS_SYSTEM, user_msg)
