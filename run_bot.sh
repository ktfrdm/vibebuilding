#!/bin/bash
# Запуск бота: останавливает ВСЕ экземпляры, затем запускает один.
# Используйте ТОЛЬКО этот скрипт для запуска бота.

cd "$(dirname "$0")"

echo "Останавливаю все экземпляры бота..."
for _ in 1 2 3 4 5; do
  pkill -9 -f "main.py" 2>/dev/null || true
  pkill -9 -f "Python.*main" 2>/dev/null || true
  pkill -9 -f "debugpy.*main" 2>/dev/null || true
  sleep 3
  RUNNING=$(pgrep -f "main.py" 2>/dev/null | wc -l)
  [ "$RUNNING" -eq 0 ] && break
  echo "  Ожидаю завершения ($RUNNING процесс(ов))..."
done

RUNNING=$(pgrep -f "main.py" 2>/dev/null | wc -l)
if [ "$RUNNING" -gt 0 ]; then
  echo "ОШИБКА: Не удалось остановить $RUNNING процесс(ов). Запустите вручную: pkill -9 -f main.py"
  exit 1
fi

echo "Запускаю единственный экземпляр бота..."
exec python3 main.py
