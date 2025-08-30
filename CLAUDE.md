# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## О проекте

micPy - приложение для записи аудио с микрофона и распознавания речи через Whisper с графическим интерфейсом на Tkinter. Поддерживает автоматический и ручной режимы записи, транскрипцию готовых аудиофайлов, копирование результата в буфер обмена и автоматическую вставку в активное окно.

## Команды разработки

### Запуск приложения
```bash
python main.py
```

### Транскрипция аудиофайла
```bash
python main.py --file path/to/audio.wav
```

### Установка зависимостей
```bash
pip install -r requirements.txt
```

## Архитектура проекта

### Основные модули (клиент)

- **main.py** (~340 строк) - точка входа, инициализация, обработка CLI аргументов, настройка IPC/D-Bus сервисов и GUI callbacks
- **settings_gui.py** (220 строк) - графический интерфейс на Tkinter с настройками, управлением записью и историей сообщений  
- **audio_recorder_client.py** (166 строк) - клиент для отправки аудио на сервер Whisper
- **dbus_service.py** - D-Bus сервис com.micpy.Recorder для системных горячих клавиш
- **ipc_server.py** - Unix Domain Socket сервер для межпроцессного взаимодействия
- **single_instance.py** (13 строк) - предотвращение запуска нескольких экземпляров
- **scripts/mic_*.sh** - bash скрипты для интеграции с системными горячими клавишами

### Паттерн архитектуры

Приложение использует callback-based архитектуру для связи между модулями:
- GUI обновляется через thread-safe callbacks (gui_set_status, gui_set_message, gui_add_history)
- AudioRecorder принимает callbacks для уведомления GUI об изменениях состояния
- Hotkeys обрабатываются в отдельном daemon thread

### Настройки и конфигурация

- **settings.json** - хранит настройки пользователя (размер модели, использование GPU, таймаут записи)
- Конфигурация загружается в main.py через load_settings()
- Поддерживает модели Whisper: tiny, base, small, medium, large
- GPU поддержка через CUDA (torch.cuda.is_available())

### Управление записью

#### CLI команды (рекомендуется)
```bash
python main.py --start     # Начать запись
python main.py --stop      # Остановить запись
python main.py --toggle    # Переключить запись
python main.py --status    # Получить статус
python main.py --quit      # Завершить приложение
```

#### Системные горячие клавиши
- Настраиваются через Ubuntu Settings → Keyboard → Custom Shortcuts
- Используют скрипты из `client/scripts/`
- Работают надежно во всех приложениях

#### IPC интерфейсы
- **Unix Domain Socket**: всегда доступен, файл `/tmp/micpy-{user}.sock`
- **D-Bus сервис**: `com.micpy.Recorder` (требует python3-dbus)

#### Старые hotkeys (нестабильно)
- **Ctrl + PrintScreen** - начать/остановить запись
- **Ctrl + Ctrl + PrintScreen** - завершить программу
- Требует флаг `--use-pynput`

### Звуковые эффекты

- **pop-long.wav** - проигрывается при начале записи
- **pop-alert.wav** - проигрывается при завершении распознавания

### Временные файлы

Приложение создает временные .wav файлы для записи аудио, которые автоматически очищаются при завершении работы.