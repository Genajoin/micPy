#!/bin/bash
# Скрипт для остановки записи микрофона через системные горячие клавиши

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/micpy_hotkeys.log"

# Функция для логирования
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [STOP] $1" >> "$LOG_FILE"
}

# Поиск python с приоритетом для venv
find_python() {
    # 1. Сначала проверяем venv в текущем проекте
    if [ -x "$CLIENT_DIR/venv/bin/python" ]; then
        echo "$CLIENT_DIR/venv/bin/python"
        return 0
    fi
    
    # 2. Пробуем python из PATH (если есть зависимости)
    for py in python3 python; do
        if command -v "$py" >/dev/null 2>&1; then
            # Проверяем, есть ли pyperclip
            if "$py" -c "import pyperclip" 2>/dev/null; then
                echo "$py"
                return 0
            fi
        fi
    done
    
    # 3. Ищем conda/miniforge окружения
    for py in /home/*/miniforge*/bin/python3 /home/*/anaconda*/bin/python3 /home/*/miniconda*/bin/python3; do
        if [ -x "$py" ] && "$py" -c "import pyperclip" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done
    
    # 4. Fallback - любой доступный python
    for py in python3 python /usr/bin/python3; do
        if command -v "$py" >/dev/null 2>&1; then
            echo "$py"
            return 0
        fi
    done
    
    return 1
}

log_message "Запуск mic_stop.sh"
log_message "CLIENT_DIR: $CLIENT_DIR"

PYTHON_EXE=$(find_python)
if [ $? -ne 0 ]; then
    log_message "ОШИБКА: Python не найден"
    exit 1
fi

log_message "Найден Python: $PYTHON_EXE"

cd "$CLIENT_DIR" || {
    log_message "ОШИБКА: Не удалось перейти в $CLIENT_DIR"
    exit 1
}

log_message "Выполнение: $PYTHON_EXE main.py --stop"
result=$("$PYTHON_EXE" main.py --stop 2>&1)
exit_code=$?

log_message "Результат: $result"
log_message "Exit code: $exit_code"

# Уведомления отключены для уменьшения засоренности вывода

exit $exit_code