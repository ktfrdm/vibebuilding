"""Конфигурация бота из .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env: сначала из корня проекта, затем из 05. Development
root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env")
load_dotenv(root / "docs" / "product-description" / "05. Development" / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

# Supabase (опционально; если не заданы, бот использует in-memory хранилище)
SUPABASE_URL = os.getenv("SUPABASE_URL") or None
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or None
