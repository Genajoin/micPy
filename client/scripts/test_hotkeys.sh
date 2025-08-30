#!/bin/bash
# Тестовый скрипт для проверки работы горячих клавиш micPy

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLIENT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/micpy_hotkeys.log"

echo "🔧 Тест системы горячих клавиш micPy"
echo "====================================="

# Переходим в директорию клиента
cd "$CLIENT_DIR" || {
    echo "❌ ОШИБКА: Не удалось перейти в $CLIENT_DIR"
    exit 1
}

echo "📁 Рабочая директория: $(pwd)"
echo ""

# Проверяем основные файлы
echo "📋 Проверка файлов:"
echo "   main.py: $([ -f main.py ] && echo '✅' || echo '❌')"
echo "   ipc_server.py: $([ -f ipc_server.py ] && echo '✅' || echo '❌')"
echo "   scripts/mic_toggle.sh: $([ -f scripts/mic_toggle.sh ] && echo '✅' || echo '❌')"
echo ""

# Проверяем статус приложения
echo "🔍 Проверка статуса приложения:"
status_result=$(python main.py --status 2>&1)
status_code=$?

if [ $status_code -eq 0 ]; then
    echo "   ✅ Приложение запущено: $status_result"
    
    echo ""
    echo "🧪 Тестирование команд:"
    
    # Тест статуса
    echo "   📊 Статус: $(python main.py --status 2>/dev/null)"
    
    # Тест toggle
    echo "   🔄 Тест Toggle..."
    toggle_result=$(python main.py --toggle 2>&1)
    echo "      Результат: $toggle_result"
    
    sleep 1
    
    # Статус после toggle
    echo "   📊 Статус после toggle: $(python main.py --status 2>/dev/null)"
    
    # Второй toggle для возврата
    echo "   🔄 Второй toggle (возврат)..."
    toggle_result2=$(python main.py --toggle 2>&1)
    echo "      Результат: $toggle_result2"
    
    echo ""
    echo "✅ Команды работают! Можно настраивать горячие клавиши в Ubuntu Settings."
    
else
    echo "   ❌ Приложение НЕ запущено: $status_result"
    echo ""
    echo "💡 Для работы горячих клавиш сначала запустите:"
    echo "   cd $CLIENT_DIR"
    echo "   python main.py"
    echo ""
    echo "   Затем настройте горячие клавиши в Settings → Keyboard → Custom Shortcuts"
fi

echo ""
echo "📝 Лог файлы для отладки:"
echo "   Горячие клавиши: $LOG_FILE"
echo "   Основное приложение: смотрите вывод в терминале где запущен python main.py"

if [ -f "$LOG_FILE" ]; then
    echo ""
    echo "📄 Последние 10 строк из $LOG_FILE:"
    tail -10 "$LOG_FILE" 2>/dev/null || echo "   (файл пуст или недоступен)"
fi