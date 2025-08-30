# micPy

**Система записи аудио с распознаванием речи через Whisper с клиент-серверной архитектурой**

micPy — это приложение для записи аудио с микрофона и транскрипции аудиофайлов, построенное на клиент-серверной архитектуре. Лёгкий клиент с графическим интерфейсом отправляет аудио на сервер с Whisper для обработки на GPU, что обеспечивает быструю транскрипцию без необходимости локальной установки ML-библиотек.

---

## 🚀 Быстрый старт

### Вариант 1: Docker (рекомендуется)

1. Запустите сервер:
   ```bash
   docker-compose up -d
   ```

2. Установите зависимости клиента:
   ```bash
   cd client
   pip install -r requirements.txt
   ```

3. Запустите клиент:
   ```bash
   python main.py
   ```

### Вариант 2: Локальная установка

#### Системные зависимости для клиента

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install portaudio19-dev python3-pyaudio xclip
```

**macOS:**
```bash
brew install portaudio
```

#### Установка клиента

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/Genajoin/micPy.git
   cd micPy/client
   ```

2. Создайте virtualenv:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/MacOS || venv\Scripts\activate  # Windows
   ```

3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

#### Установка сервера

1. Установите системные зависимости:
   ```bash
   # Linux
   sudo apt install ffmpeg
   
   # macOS
   brew install ffmpeg
   ```

2. Установите Python зависимости:
   ```bash
   cd server
   pip install -r requirements.txt
   ```

3. Запустите сервер:
   ```bash
   python main.py
   ```

---

## 📱 Использование

### Запуск клиента

```bash
cd client
python main.py
```

### Конфигурация сервера

Настройте сервер через переменные окружения в `docker-compose.yml` или `.env`:

```bash
WHISPER_MODEL_SIZE=medium  # tiny, base, small, medium, large
PORT=8000
```

### Транскрипция аудиофайла (CLI)

Для распознавания текста из готового аудиофайла используйте:
```bash
cd client
python main.py --file путь/к/вашему/файлу.mp3
```

### Графический интерфейс

![image.png](image.png)

Клиент предоставляет простой интерфейс:
- **URL сервера** — адрес сервера распознавания (по умолчанию http://localhost:8000)
- **Длительность записи** — максимальное время записи в автоматическом режиме
- **Кнопка транскрипции файла** — выбор и обработка готовых аудиофайлов
- **Ручное управление записью** — кнопки "Начать/Остановить запись" 
- **История сообщений** — последние результаты транскрипции
- **Статус** — текущее состояние работы

Настройки сохраняются в `client/settings.json`.

### Режимы управления

#### 1. Ручной режим (в GUI)
- **Кнопки "Начать/Остановить запись"** — запись не ограничена таймером

#### 2. CLI команды (рекомендуется для системных горячих клавиш)
```bash
python main.py --start    # Начать запись
python main.py --stop     # Остановить запись  
python main.py --toggle   # Переключить запись
python main.py --status   # Получить статус
python main.py --quit     # Завершить приложение
```

#### 3. Системные горячие клавиши Ubuntu

**Пошаговая настройка:**

1. Откройте **Settings → Keyboard → View and Customize Shortcuts**
2. Прокрутите вниз и нажмите **Custom Shortcuts**
3. Нажмите **Add Shortcut** и создайте ярлыки:

**Основное управление:**
- **Название**: micPy Toggle Recording
- **Команда**: `/home/gena/dev/micPy/client/scripts/mic_toggle.sh`
- **Сочетание**: Ctrl+PrintScreen

**Дополнительные команды:**
- **Название**: micPy Start Recording  
- **Команда**: `/home/gena/dev/micPy/client/scripts/mic_start.sh`
- **Сочетание**: Ctrl+Alt+R

- **Название**: micPy Stop Recording
- **Команда**: `/home/gena/dev/micPy/client/scripts/mic_stop.sh`  
- **Сочетание**: Ctrl+Alt+T

💡 **Важно:** 
- Замените `/home/gena/dev/micPy` на ваш реальный путь к проекту
- Скрипты автоматически найдут правильный Python (venv → conda → системный)
- Перед использованием горячих клавиш запустите основное приложение: `python main.py`

#### 4. D-Bus интерфейс (для продвинутых пользователей)
```bash
# Через D-Bus
dbus-send --session --dest=com.micpy.Recorder \
  --type=method_call /com/micpy/Recorder \
  com.micpy.Recorder.ToggleRecording
```

#### 5. Старый режим (pynput)
```bash
python main.py --use-pynput
```
- **Ctrl + PrintScreen** — переключить запись
- **Ctrl + Ctrl + PrintScreen** — завершить программу

⚠️ **Старый режим работает нестабильно в терминалах**

### Процесс работы

1. **Запуск сервера** — обрабатывает аудио через Whisper на GPU
2. **Запуск клиента** — предоставляет интерфейс записи и управления
3. **Запись аудио**:
   - **Системные горячие клавиши**: Ctrl + PrintScreen (рекомендуется)
   - **CLI команды**: `python main.py --toggle`
   - **Ручное управление**: кнопки в GUI
   - Воспроизводятся звуковые сигналы (`pop-long.wav`, `pop-alert.wav`)
4. **Обработка**:
   - Аудио кодируется в base64 и отправляется на сервер
   - Сервер транскрибирует через Whisper
   - Результат возвращается клиенту
5. **Результат**:
   - Текст копируется в буфер обмена
   - Автоматически вставляется в активное окно (Ctrl+V)
   - Добавляется в историю сообщений

### Установка системных зависимостей для D-Bus

```bash
# Ubuntu/Debian
sudo apt install python3-dbus python3-gi

# Архитектура
# Клиент поддерживает несколько способов управления:
# 1. IPC через Unix Domain Socket (работает всегда)
# 2. D-Bus сервис (требует python3-dbus)
# 3. Старый pynput режим (флаг --use-pynput)
```

---

## 🏗️ Архитектура

### Клиент-серверная модель

- **Клиент** (`client/`) — лёгкий интерфейс без ML-зависимостей
- **Сервер** (`server/`) — FastAPI с Whisper на GPU для быстрой обработки
- **Общие модули** (`common/`) — схемы данных и утилиты

### Структура проекта

```
micPy/
├── client/                    # Клиентское приложение
│   ├── main.py               # Точка входа клиента
│   ├── settings_gui.py       # Графический интерфейс 
│   ├── audio_recorder_client.py  # Запись и отправка на сервер
│   ├── single_instance.py    # Предотвращение множественных запусков
│   └── requirements.txt      # Зависимости клиента
├── server/                   # Сервер обработки
│   ├── main.py               # FastAPI сервер с Whisper
│   ├── requirements.txt      # Зависимости сервера
│   └── Dockerfile           # Контейнеризация сервера
├── common/                   # Общие компоненты
│   ├── schemas.py           # Pydantic схемы API
│   └── audio_utils.py       # Утилиты работы с аудио
├── docker-compose.yml        # Продакшн конфигурация
├── docker-compose.dev.yml    # Конфигурация для разработки
└── .env.example             # Пример переменных окружения
```

## ⚙️ Конфигурация

### Переменные окружения сервера

- `WHISPER_MODEL_SIZE` — размер модели (tiny, base, small, medium, large)
- `PORT` — порт API сервера

### Настройки клиента

- Сохраняются в `client/settings.json`
- URL сервера, длительность записи

---

## 🛠️ Инструменты и библиотеки
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/Genajoin/micPy/bandit.yml)](https://github.com/Genajoin/micPy/actions)
[![CodeFactor](https://img.shields.io/codefactor/grade/github/Genajoin/micPy?style=flat-square)](https://www.codefactor.io/repository/github/Genajoin/micPy)

---

## 👤 Авторы

- [Истомин Евгений]

---

## 📜 Лицензия

MIT License © 2025