# micPy

**Speech-to-Text клиент для OpenAI-совместимого API**

micPy — это терминальный клиент для распознавания речи использующий OpenAI-совместимый API. Поддерживает интерактивный TUI редактор и фоновый демон для голосового ввода по триггеру - hook на комбинацию клавиш.

---

## 🚀 Быстрый старт

### Системные зависимости

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install portaudio19-dev python3-pyaudio xclip
```

**macOS:**
```bash
brew install portaudio
```

### Установка

```bash
git clone https://github.com/Genajoin/micPy.git
cd micPy
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 📱 Использование

### Команды

```bash
micpy                          # TUI редактор (интерактивный)
micpy --api-url http://localhost:5092/v1  # Указать API URL
micpy --test                   # Тестовый режим

micpy daemon                   # Фоновый сервис голосового ввода
micpy trigger                  # Отправить триггер на демон

mic-stream                     # Алиас для micpy
```

### TUI Редактор

Интерактивный терминальный редактор с голосовым вводом:

| Клавиша | Действие |
|---------|----------|
| F1 | Показать/скрыть справку |
| F5 | Начать/остановить запись |
| F3 | Копировать весь текст |
| F8 | Очистить текст |
| Ctrl+A | Выделить все |
| Ctrl+C / Ctrl+Q | Выход |

### Фоновый демон

Для голосового ввода по горячей клавише:

1. Запустите демон:
   ```bash
   micpy daemon &
   ```

2. Привяжите триггер к хоткею в DE:
   ```bash
   micpy trigger
   ```

 - **GNOME:** Settings → Keyboard → Custom Shortcuts
 - **KDE:** System Settings → Shortcuts

3. Нажмите хоткей для начала записи, ещё раз — для остановки и транскрипции

### Запуск демона через systemd

Для автозапуска демона при входе в систему:

1. Создайте файл сервиса:
   ```bash
   nano ~/.config/systemd/user/micpy-daemon.service
   ```

2. Содержимое файла:
   ```ini
   [Unit]
   Description=MicPy Voice Input Daemon
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/path/to/micPy
   ExecStart=/path/to/micPy/.venv/bin/micpy daemon
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

   Замените `/path/to/micPy` на реальный путь к проекту.

3. Активируйте сервис:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable micpy-daemon
   systemctl --user start micpy-daemon
   ```

4. Проверьте статус:
   ```bash
   systemctl --user status micpy-daemon
   ```

5. Логи:
   ```bash
   journalctl --user -u micpy-daemon -f
   ```

---

## ⚙️ Конфигурация

### Переменные окружения

Создайте `.env` файл:

```bash
PARAKEET_API_URL=http://localhost:5092/v1
PARAKEET_MODEL=parakeet-tdt-0.6b-v3
```

Поиск `.env`:
- `./.env`
- `~/.env`
- `~/micpy.env`
- `~/.config/micpy/.env`

### Аргументы

| Аргумент | По умолчанию | Описание |
|----------|--------------|----------|
| `--api-url` | http://localhost:5092/v1 | URL Parakeet API |
| `--model` | parakeet-tdt-0.6b-v3 | Модель транскрипции |
| `--test` | - | Тестовый режим |

---

## 🏗️ Архитектура

```
micPy/
├── client/
│   ├── cli.py                # CLI точка входа
│   ├── minimal_editor.py     # TUI редактор
│   ├── voice_daemon.py       # Фоновый демон
│   ├── audio_buffer.py       # Захват аудио
│   ├── parakeet_client.py    # HTTP клиент к API
│   └── single_instance.py    # Блокировка повторных запусков
├── pyproject.toml
└── README.md
```

---

## 🔗 Требования к API

Требуется OpenAI-совместимый STT эндпоинт:

- `POST /v1/audio/transcriptions` — транскрипция аудио
- `GET /health` — проверка доступности (опционально)

Рекомендуемый на начало 2026 - Parakeet-tdt-0.6b-v3 с инференсом на CPU.
Рекомендуемый способ установки с использованием Docker Compose:

```bash
git clone https://github.com/groxaxo/parakeet-tdt-0.6b-v3-fastapi-openai
cd parakeet-tdt-0.6b-v3-fastapi-openai
docker compose up parakeet-cpu -d
```
---

## 👤 Автор

[Истомин Евгений]

## 📜 Лицензия

MIT License © 2025
