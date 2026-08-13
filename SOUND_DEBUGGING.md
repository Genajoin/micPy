# Отладка звука уведомлений micPy

## Симптомы

1. Звук старта записи (`start`) — срабатывает нестабильно (иногда нет)
2. Звук окончания транскрипции (`end`) — не срабатывает на длинных записях
3. Раньше (с canberra-gtk-play) — не срабатывал почти никогда

## Окружение

- OS: Linux (Ubuntu/Noble), Wayland (GNOME)
- Audio: PipeWire (+ PulseAudio совместимость)
- Демон: systemd user service (`micpy-daemon.service`)
- ENV демона: `DBUS_SESSION_BUS_ADDRESS`, `XDG_RUNTIME_DIR=/run/user/1000`
  (НЕТ `DISPLAY`, НЕТ `WAYLAND_DISPLAY`)

## Доступные инструменты воспроизведения

| Инструмент | Установлен | Работает в окружении демона | Создаёт PipeWire поток |
|---|---|---|---|
| `canberra-gtk-play` | да | exit=0, но **не играет** | **нет** |
| `pw-play` | да | **да** | **да** |
| `paplay` | нет | — | — |
| `aplay` | да | **нет** ("Host is down") | — |

### Почему canberra-gtk-play не работал

Звуковая тема GNOME: `__custom` — **директории `/usr/share/sounds/__custom/` не существует**.
canberra-gtk-play ищет event sounds (`bell`, `message`) в текущей теме, не находит,
и **молча возвращает exit=0**, не создавая аудиопоток.

Доказательство: `pw-cli ls` показывает Playback-поток при `pw-play`, но **ничего** при `canberra-gtk-play`.

## Эксперимент 1: canberra-gtk-play (оригинальный код)

**Код:** `subprocess.run(['canberra-gtk-play', '-i', sound_name], timeout=2)`

**Результат:** Звук почти никогда не слышен. canberra-gtk-play молча падает из-за темы `__custom`.
Fallback на `print('\a')` (терминальный bell) бесполезен — демон работает без терминала.

**Вывод:** canberra-gtk-play непригоден. Нужен прямой проигрыватель.

## Эксперимент 2: pw-play через subprocess.run в daemon-треде

**Код:**
```python
# voice_daemon.py
threading.Thread(target=play_sound, args=('end',), daemon=True).start()

# audio_buffer.py — play_sound
subprocess.run(['pw-play', wav_path], timeout=2)  # блокирующий
```

**Генерация WAV:** 16kHz mono, 600Hz (start, 80ms) / 1200Hz (end, 120ms), с fade in/out.

**Результат:** Звук слышен, но нестабильно. Иногда старт, иногда конец, иногда оба.
Пользователь: "работает как-то нестабильно. Сейчас не услышал старт, но услышал окончание."

**Гипотеза причины:** `subprocess.run` блокирует daemon-тред. GIL + планировщик потоков
могут задерживать запуск. Два соединения с PipeWire (PyAudio input + pw-play output)
в один момент могут конфликтовать.

## Эксперимент 3: pw-play через Popen, без тредов (текущая версия)

**Код:**
```python
# audio_buffer.py — play_sound
subprocess.Popen(
    ['pw-play', wav_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True  # оторванный процесс
)

# voice_daemon.py — вызов напрямую, без threading.Thread
play_sound('start')  # Popen возвращается мгновенно
```

**Результат:** Значительно стабильнее. Но:
- **Старт:** иногда не срабатывает (связано с инициализацией PyAudio?)
- **Окончание:** не срабатывает на длинных записях (короткие — OK)

**Нерешённые вопросы:**
1. Почему старт иногда пропускается? Конфликт PipeWire-соединений при открытии input stream?
2. Почему конец не работает на длинных записях? API latency? Timeout? Состояние PipeWire?

## План дальнейших экспериментов

### Эксперимент 4: Старт — играть ДО инициализации PyAudio

Гипотеза: PyAudio initialization (открытие input stream) и pw-play (открытие output stream)
конкурируют за PipeWire соединение. Решение: play_sound('start') ВЫЗЫВАТЬ ДО start_recording().

**Результат:** Не помогло. Звук старта по-прежнему нестабилен.

### Эксперимент 5: Окончание — детальная диагностика

Добавлено логирование каждого этапа PyAudio playback: open_pa, open_stream, write.

**Результат:** PyAudio **каждый раз** сообщает успех (open_pa=~200ms, write=~100ms).
Логи показывают "played via pyaudio" для ВСЕХ звуков, включая длинные записи.
Но пользователь их не слышит. **PyAudio пишет в буфер, но PipeWire молча глотает звук.**

### Эксперимент 6: Воспроизведение через PyAudio с drain

Добавлен `time.sleep(audio_ms + 50ms)` после `stream.write()` перед закрытием stream.

**Результат:** PyAudio по-прежнему сообщает успех, но звук не доходит до колонок.
Проблема не в буферизации, а в маршрутизации PipeWire.

## Эксперимент 7: РЕШЕНИЕ — оторванный pw-play с чистым окружением (финальный)

**Код:**
```python
clean_env = {
    'XDG_RUNTIME_DIR': f'/run/user/{uid}',
    'PATH': '/usr/bin:/bin:/usr/local/bin',
    'HOME': os.path.expanduser('~'),
    'LANG': 'en_US.UTF-8',
}
delay = '0.15' if sound_type == 'end' else '0'
subprocess.Popen(
    ['bash', '-c', f'sleep {delay} && exec pw-play "{wav_path}"'],
    env=clean_env,
    start_new_session=True
)
```

**Три ключевых отличия от предыдущих попыток:**

1. **Чистое окружение** — pw-play не наследует переменные демона (включая возможные
   ALSA/PortAudio артефакты). PipeWire видит чистый новый клиент.
2. **Задержка 150мс для end-звука** — PipeWire успевает освободить ресурсы input stream
   (записи) до того, как pw-play открывает output stream.
3. **Полностью оторванный процесс** — `start_new_session=True` + `exec pw-play`
   гарантируют независимый процесс group/session.

**Результат:** Стабильно работает при любой длительности записи (проверено на 2-30+ сек).
Звук старта и окончания отрабатывает корректно во всех циклах записи.

**PyAudio остался как fallback** для систем без pw-play.

## Корень проблемы (итог)

Проблема была в PipeWire, который **молча игнорировал** аудио от процесса демона.
PyAudio/ALSA сообщали об успехе (данные в буфере), но PipeWire не маршрутизировал
их на sink (колонки). Причина: процесс демона, открывающий/закрывающий input streams
(микрофон), попадал в состояние, при котором PipeWire не обрабатывал его output streams.

Решение: играть звук через **отдельный процесс** с **чистым PipeWire-окружением** и
**задержкой** для освобождения ресурсов записи.
