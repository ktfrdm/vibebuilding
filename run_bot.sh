#!/bin/bash
# Запуск бота: останавливает ВСЕ экземпляры, затем запускает один.
# Используйте ТОЛЬКО этот скрипт для запуска бота.

cd "$(dirname "$0")"

echo "Останавливаю все экземпляры бота..."
pkill -9 -f "python3 main.py" 2>/dev/null || true
pkill -9 -f "python.*main.py" 2>/dev/null || true
pkill -9 -f "Python main.py" 2>/dev/null || true
sleep 4

# Проверка: не осталось ли процессов
RUNNING=$(pgrep -f "Python main.py" 2>/dev/null | wc -l)
if [ "$RUNNING" -gt 0 ]; then
  echo "Предупреждение: всё ещё запущено $RUNNING процесс(ов). Жду ещё..."
  sleep 3
  pkill -9 -f "Python main.py" 2>/dev/null || true
  pkill -9 -f "main.py" 2>/dev/null || true
  sleep 2
fi

echo "Запускаю единственный экземпляр бота..."
exec python3 main.py
