# micPy

**Аудиозапись с микрофона с распознаванием речи через Whisper**

Простое приложение для записи аудио с микрофона, использующее звуковые эффекты (pop-alert.wav и pop-long.wav). Предотвращает запуск нескольких экземпляров через single_instance.py. Распознает речь с помощью модели Whisper и копирует результат в буфер обмена.

---

## 🚀 Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/Genajoin/micPy.git
   ```
2. Создайте virtualenv (рекомендуется):
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/MacOS || venv\Scripts\activate  # Windows
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt 
   ```
4. Установите Whisper и Torch:
   ```bash
   pip install git+https://github.com/openai/whisper.git
   pip install torch
   ```

---

## 📱 Использование

Запустите приложение:
```bash
python main.py
```

### Горячие клавиши

- **Ctrl + PrintScreen** — начать или остановить запись (максимум 30 секунд).
- **Ctrl + Ctrl + PrintScreen** — завершить работу программы.

---

## ⚙️ Процесс работы

- При запуске активируется слушатель клавиш.
- При нажатии **Ctrl + PrintScreen**:
  - проигрывается звук `pop-long.wav`,
  - начинается запись аудио с микрофона.
- Запись длится максимум 30 секунд или до повторного нажатия.
- После окончания:
  - аудио сохраняется во временный файл `/tmp/micpy-output.wav`,
  - передается в модель Whisper для распознавания речи,
  - распознанный текст копируется в буфер обмена,
  - автоматически вставляется в активное окно (эмулируется Ctrl+V),
  - проигрывается звук `pop-alert.wav`.
- Для предотвращения запуска нескольких копий используется lock-файл `/tmp/micpy.lock`.

---

## 🧠 Использование Whisper

- Используется модель **Whisper** от OpenAI.
- По умолчанию загружается модель `"medium"`.
- Для ускорения можно включить использование GPU, изменив в коде:
  ```python
  try_cuda = True
  ```
- Для работы требуется установленный whisper и torch.

---

## 📋 Зависимости

- `pyaudio`
- `soundfile`
- `whisper`
- `torch`
- `pyperclip`
- `pynput`
- `keyboard`
- стандартные библиотеки Python: threading, io, os, time, atexit, signal, logging

---

## 🛠️ Инструменты и библиотеки
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/Genajoin/micPy/main.yml?style=flat-square)](https://github.com/Genajoin/micPy/actions)
[![CodeFactor](https://img.shields.io/codefactor/grade/github/Genajoin/micPy?style=flat-square)](https://www.codefactor.io/repository/github/Genajoin/micPy)

---

## 👤 Авторы

- [Истомин Евгений]

---

## 📜 Лицензия

MIT License © 2025