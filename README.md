# Вайб — бот для согласования встреч

## Описание

Бот помогает организатору создать встречу, собрать ответы участников по слотам и выбрать итоговое время. MVP: хранение в памяти, без БД.

## Запуск

**Важно:** Запускайте бота **только** через `run_bot.sh` — иначе возможны конфликты при нескольких экземплярах.

```bash
pip install -r requirements.txt
./run_bot.sh
```

Ключи загружаются из `.env` в корне или из `docs/product-description/05. Development/.env`.

## Ключи

Скопируйте `.env.example` в `.env` и укажите:
- **BOT_TOKEN** (или TELEGRAM_BOT_TOKEN) — токен от @BotFather в Telegram
- **OPENAI_API_KEY** — ключ OpenAI для парсинга дат (https://platform.openai.com/api-keys)

## Документация

- `docs/product-description/` — продуктовое описание, сценарии, исследования, бэклог
- `docs/product-description/05. Development/` — гайды к разработке:
  - [PLAN_IMPLEMENTATION.md](docs/product-description/05.%20Development/PLAN_IMPLEMENTATION.md) — план реализации
  - [IMPLEMENTATION.md](docs/product-description/05.%20Development/IMPLEMENTATION.md) — спецификация и план
