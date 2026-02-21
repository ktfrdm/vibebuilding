# Документация реализации бота Вайб

**План и спецификация** для реализации MVP Telegram-бота для согласования встреч. Код удалён — реализация с нуля по [PLAN_IMPLEMENTATION.md](PLAN_IMPLEMENTATION.md).

Связанные документы: [BOT_DEV_SUMMARY.md](BOT_DEV_SUMMARY.md), [BOT_FLOW_MVP.md](../03.%20Scenarios/BOT_FLOW_MVP.md), [BOT_VOICE_AND_TEXTS.md](../03.%20Scenarios/BOT_VOICE_AND_TEXTS.md).

---

## 1. Обзор

Бот помогает организатору создать встречу, собрать ответы участников по слотам и выбрать итоговое время. Данные хранятся в памяти (без БД). Запуск локальный.

**Основные ограничения MVP:**
- Локальный запуск; данные в памяти, теряются при перезапуске
- База данных на текущем этапе не используется
- Нет меню «Мои встречи», напоминаний

---

## 2. Технологии

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.9+ |
| Фреймворк бота | python-telegram-bot 21+ |
| Парсинг дат | **только через LLM** — OpenAI API (gpt-4o-mini) |
| Конфигурация | python-dotenv, `.env` |

**Важно:** Обработка дат и слотов выполняется **только через LLM**. В коде бота парсинга дат нет — LLM возвращает слоты в готовом формате.

---

## 3. Структура проекта (целевая)

```
Вайб/
├── main.py                 # Точка входа (создать)
├── requirements.txt       # Зависимости (создать)
├── .env.example            # Шаблон ключей (есть)
├── bot/
│   ├── config.py           # BOT_TOKEN, OPENAI_API_KEY из .env
│   ├── storage.py          # user_states (storage-based state)
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
- `id`, `title`, `slots`, `status` (`created` | `time_chosen`)
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

## 6. Состояние организатора (storage)

Состояние хранится в `user_states` ([bot/storage.py](bot/storage.py)): `step` (idle | title | slots | slots_confirm | place) и `data`. Без FSM.

**Callback-хендлеры организатора** (skip, slots_ok, slots_edit, place_skip) срабатывают только в своём шаге. При несовпадении `get_user_step(uid)` с ожидаемым вызывается `query.answer()` и обработка завершается без изменения состояния.

### Таблица состояний организатора

| Шаг организатора | user_states[uid].step | data | Триггер перехода |
|------------------|------------------------|------|-------------------|
| Начало | — | — | «Давай соберёмся!» |
| Название | title | {} | текст или callback skip |
| Опции (слоты) | slots | {title} | текст (LLM) |
| Подтверждение слотов | slots_confirm | {title, slots} | callback slots_ok или slots_edit |
| Создана | — | — | slots_ok → clear |
| Место | place | {meeting_id} | текст или callback place_skip |
| Рассылка | — | — | место введено/пропущено → clear |

---

## 6a. Очередь запросов (per-user)

Чтобы избежать гонок при параллельных действиях одного пользователя, используется `PerUserUpdateProcessor` ([bot/queue.py](bot/queue.py)): обновления **одного пользователя** обрабатываются строго по порядку. Разные пользователи — параллельно (до 32 одновременно).

Без очереди быстрый клик по нескольким кнопкам или несколько сообщений подряд могли бы обрабатываться одновременно и конфликтовать с состоянием (`user_states`, `participant_selection`).

---

## 7. Обработчики и порядок регистрации

Порядок в [main.py](main.py) критичен:

1. **start** — `CommandHandler("start")`: без deep link — сброс, главное меню; с deep link `meeting_xxx` — participant flow
2. **help** — `CommandHandler("help")`
3. **callbacks** — `CallbackQueryHandler` для slot_toggle, decline, done, skip, slots_ok, slots_edit, choose_slot, place_skip, confirm_yes, confirm_no
4. **organizer** — `MessageHandler(filters.TEXT)`: текст организатора по step из user_states
5. **fallback** — `MessageHandler(filters.ALL)`: «Отправь текст» в активном flow

**Команда /start** без аргументов сбрасывает состояние (`clear_user_state`) и показывает главное меню. С аргументом `meeting_xxx` — deep link к встрече (participant или сводка организатора).

---

## 8. Парсинг опций (services/llm.py)

**Обработка дат и слотов — только через LLM (OpenAI API).** В коде бота парсинга дат из текста нет.

LLM получает текст организатора и возвращает готовый список слотов в формате `[{date, time, datetime}, ...]`.

**Ограничение:** Даты и время всегда в будущем. Нельзя назначить встречу в прошлом. LLM-промпт требует будущие даты; в `llm.py` есть `filter_past_slots()` — дополнительная проверка по полю `datetime`.

Примеры ввода: «суббота 12:00, 15:00, 18:00»; «в эту субботу»; «25 февраля вечером»; «следующие выходные с 12 до 18».

Используется ключ `OPENAI_API_KEY` из `.env`.

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

**Важно:** Должен быть запущен только один экземпляр бота. Используйте скрипт `run_bot.sh` — он останавливает все экземпляры и запускает один.

```bash
pip install -r requirements.txt
./run_bot.sh
```

Ключи — в `.env` (скопировать из `.env.example`). Скрипт `run_bot.sh` в корне проекта — единственная точка входа для запуска.

---

## 13. Что не реализовано (MVP)

- База данных (на текущем этапе не планируется)
- «Мои встречи»
- Напоминания не ответившим
- Редактирование/отмена встречи
- Предложение слота участником
