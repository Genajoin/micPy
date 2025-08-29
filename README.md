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

- **Ручной режим**: используйте кнопки "Начать запись" и "Остановить запись" — запись не ограничена таймером.
- **Автоматический режим**: используйте горячие клавиши:
  - **Ctrl + PrintScreen** — начать (максимальная длительность из настроек) или остановить запись.
  - **Ctrl + Ctrl + PrintScreen** — завершить работу программы.

### Процесс работы

1. **Запуск сервера** — обрабатывает аудио через Whisper на GPU
2. **Запуск клиента** — предоставляет интерфейс записи и управления
3. **Запись аудио**:
   - Горячие клавиши: Ctrl + PrintScreen (старт/стоп)
   - Ручное управление: кнопки в интерфейсе
   - Воспроизводятся звуковые сигналы (`pop-long.wav`, `pop-alert.wav`)
4. **Обработка**:
   - Аудио кодируется в base64 и отправляется на сервер
   - Сервер транскрибирует через Whisper
   - Результат возвращается клиенту
5. **Результат**:
   - Текст копируется в буфер обмена
   - Автоматически вставляется в активное окно (Ctrl+V)
   - Добавляется в историю сообщений

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