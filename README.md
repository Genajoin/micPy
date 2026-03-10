# micPy

**Speech-to-Text клиент для OpenAI-совместимого API**

micPy — это терминальный клиент для распознавания речи использующий OpenAI-совместимый API. Поддерживает интерактивный TUI редактор и фоновый демон для голосового ввода по триггеру - hook на комбинацию клавиш.

---

## 🚀 Быстрый старт

### Системные зависимости

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install portaudio19-dev python3-pyaudio xclip wl-clipboard
```

> `xclip` для X11, `wl-clipboard` для Wayland. Можно установить оба.

**Для автоматической вставки текста на Wayland:**
```bash
sudo apt install wtype
```

> `wtype` позволяет вставлять текст напрямую в активное окно без нажатия Ctrl+V. Без него текст копируется в буфер обмена.

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
   micpy daemon --output-mode clipboard  # Только буфер обмена
   ```

**Режимы вывода текста (--output-mode):**
- `auto` — wtype если установлен, иначе clipboard (по умолчанию)
- `injection` — только прямая вставка через wtype (требует wtype)
- `clipboard` — только буфер обмена (Ctrl+V)

**Ограничения Wayland:**
- На Wayland текст вставляется в **текущее активное окно**
- Оставайтесь в целевом окне во время записи и после неё
- xdotool/pynput не работают на Wayland

**GNOME/Wayland:** clipboard — единственный рабочий вариант для русского текста.

| Инструмент | Sway/Hyprland | GNOME/Wayland | Unicode |
|------------|---------------|---------------|---------|
| wtype | ✅ | ❌ Нет virtual keyboard | ✅ |
| pynput | ❌ | ❌ Требует X11 | ✅ |
| ydotool | ✅ | ✅ Но нужен root | ❌ |

> Автоматическая вставка на GNOME/Wayland невозможна без root — это ограничение GNOME.

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
   # Передаём переменные для работы с буфером обмена на Wayland/X11
   PassEnvironment=WAYLAND_DISPLAY DISPLAY

   [Install]
   WantedBy=default.target
   ```

   Замените `/path/to/micPy` на реальный путь к проекту.

   > **Важно:** `PassEnvironment` обязателен для работы буфера обмена. Без него демон не сможет скопировать текст в clipboard на Wayland/X11.

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
| `--output-mode` | auto | Режим вывода (daemon): auto/injection/clipboard |

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
