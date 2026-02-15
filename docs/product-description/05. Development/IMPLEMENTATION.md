# Документация реализации бота Вайб

**План и спецификация** для реализации MVP Telegram-бота для согласования встреч. Код удалён — реализация с нуля по [PLAN_IMPLEMENTATION.md](PLAN_IMPLEMENTATION.md).

Связанные документы: [BOT_DEV_SUMMARY.md](BOT_DEV_SUMMARY.md), [BOT_FLOW_MVP.md](../03.%20Scenarios/BOT_FLOW_MVP.md), [BOT_VOICE_AND_TEXTS.md](../03.%20Scenarios/BOT_VOICE_AND_TEXTS.md).

---

## 1. Обзор

Бот помогает организатору создать встречу, собрать ответы участников по слотам и выбрать итоговое время. Данные хранятся в памяти (без БД). Запуск локальный.

**Основные ограничения MVP:**
- Данные теряются при перезапуске бота
- Нет персистентного хранилища (SQLite и т.п.)
- Нет меню «Мои встречи», напоминаний

---

## 2. Технологии

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.9+ |
| Фреймворк бота | aiogram 3.13+ |
| Парсинг дат | dateparser 1.2+ |
| LLM (период, слоты) | OpenAI API (gpt-4o-mini) |
| Конфигурация | python-dotenv, `.env` |

---

## 3. Структура проекта (целевая)

```
Вайб/
├── main.py                 # Точка входа (создать)
├── requirements.txt       # Зависимости (создать)
├── .env.example            # Шаблон ключей (есть)
├── bot/                    # Создать при реализации
│   ├── bot.py
│   ├── config.py           # BOT_TOKEN, OPENAI_API_KEY из .env
│   ├── storage.py
│   ├── states.py
│   ├── handlers/
│   ├── keyboards/
│   └── services/
└── docs/product-description/05. Development/
    ├── .env.example        # Ключи Telegram и OpenAI
    ├── BOT_DEV_SUMMARY.md
    ├── PLAN_IMPLEMENTATION.md
    └── IMPLEMENTATION.md
```

---

## 4. Хранилище (storage.py)

In-memory словари:

**meetings** — `dict[meeting_id, Meeting]`:
- `id`, `title`, `period`, `slots`, `status` (`created` | `time_chosen`)
- `creator_user_id`, `chat_id`, `chosen_slot_id`, `place`

**participants** — `dict[(meeting_id, user_id), ParticipantData]`:
- `status` (`replied` | `declined` | `pending`)
- `chosen_slot_ids` — список индексов удобных слотов
- `pending_confirm` — ожидание ответа «Сможешь прийти?»

**participant_selection** (в participant.py) — временный выбор слотов до нажатия «Готово».

---

## 5. Конфигурация и ключи

См. `.env.example` в корне и в `05. Development/`.

Переменные:
- `BOT_TOKEN` (или `TELEGRAM_BOT_TOKEN`) — токен от @BotFather в Telegram
- `OPENAI_API_KEY` — ключ OpenAI для LLM-парсинга (https://platform.openai.com/api-keys)
- `LOG_LEVEL` (по умолчанию INFO)
- `DEBUG` (по умолчанию false)

---

## 6. FSM (states.py)

| StatesGroup | Состояния | Назначение |
|-------------|-----------|------------|
| CreateMeeting | title, period, slots, slots_confirm | Создание встречи организатором |
| ChoosePlace | place | Ввод места после выбора слота |

Хранение FSM: `MemoryStorage` (в памяти).

---

## 7. Обработчики и порядок роутеров

Порядок в `bot.py` критичен:

1. **start** — `/start` без deep link: сброс FSM, главное меню с кнопкой «Давай соберёмся!»
2. **participant** — `/start meeting_xxx`: deep link участника или организатора
3. **organizer** — FSM организатора; фильтр `~CommandStart()` чтобы не перехватывать `/start`
4. **notifications** — «Да, приду!» / «Увы, не смогу»
5. **common** — `/help`

**Команда /start** всегда сбрасывает сценарий (`state.clear()`) и показывает главное меню. Реализация: `StartResetMiddleware` на `dp.update` перехватывает текст «start»/«/start» до любых handler; плюс проверка в handler'ах организатора как страховка. Исключение: `/start meeting_xxx` — deep link.

---

## 8. Парсинг дат (services/llm.py)

Двухступенчатый парсинг: **dateparser** → **OpenAI** (fallback).

**dateparser** обрабатывает:
- Период: «25 февраля», «в эту субботу», «завтра», «7–8 марта», «16.02»
- Слоты: «суббота 12:00, 15:00, 18:00», «завтра 15:00», «16.02 15:00»

**Предобработка:** форматы `DD.MM` и `D.MM` без года дополняются текущим годом (например, `16.02` → `16.02.2026`).

**LLM** используется при неудаче dateparser. Промпты передают текущую дату и контекст периода.

---

## 9. Deep link и участник

Ссылка: `t.me/<bot_username>?start=meeting_<meeting_id>`

Payload: `meeting_m_xxxxxxxxxxxx` (id в storage — `m_xxxxxxxxxxxx`).

**Организатор** по ссылке видит сводку ответов и выбирает слот.
**Участник** — слоты, кнопки «удобно» (toggle), «Увы не смогу», «Готово».

---

## 10. Рассылка уведомлений

После выбора организатором слота и места:

- **Отметившим слот** — сразу полное подтверждение (дата, время, место).
- **Не отметившим** — вопрос «Сможешь прийти?» с кнопками «Да, приду!» / «Увы, не смогу».
- **Отказавшимся** («не смогу») — уведомления не отправляются.

---

## 11. Обработка ошибок

- **Глобальный handler** (`dp.error.register`): при любой ошибке пользователю отправляется «Что-то пошло не так. Нажми /start и попробуй снова».
- **В handler’ах организатора**: `try/except`, при ошибке — понятное сообщение.
- **Fallback handler’ы**: если в FSM отправлено не текст (например, фото без подписи) — подсказка отправить текст.

---

## 12. Запуск

После реализации:
```bash
pip install -r requirements.txt
python main.py
```

Ключи — в `.env` (скопировать из `.env.example`).

---

## 13. Что не реализовано (MVP)

- SQLite или другое персистентное хранилище
- «Мои встречи»
- Напоминания не ответившим
- Редактирование/отмена встречи
- Предложение слота участником
