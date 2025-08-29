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

### Основные модули

- **main.py** (236 строк) - точка входа, инициализация Whisper модели, обработка аргументов CLI, настройка hotkeys и GUI callbacks
- **settings_gui.py** (220 строк) - графический интерфейс на Tkinter с настройками модели, управлением записью и историей сообщений
- **audio_recorder.py** (124 строк) - класс AudioRecorder для управления записью аудио через pyaudio и транскрипцией через Whisper
- **single_instance.py** (13 строк) - предотвращение запуска нескольких экземпляров приложения

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

### Hotkeys

- **Ctrl + PrintScreen** - начать/остановить запись
- **Ctrl + Ctrl + PrintScreen** - завершить программу

### Звуковые эффекты

- **pop-long.wav** - проигрывается при начале записи
- **pop-alert.wav** - проигрывается при завершении распознавания

### Временные файлы

Приложение создает временные .wav файлы для записи аудио, которые автоматически очищаются при завершении работы.