import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os

MODEL_SIZES = ["tiny", "base", "small", "medium", "large"]

class SettingsWindow(tk.Tk):
    SETTINGS_FILE = "settings.json"

    def __init__(self, manual_start_callback=None, manual_stop_callback=None, model=None):
        super().__init__()
        self.manual_start_callback = manual_start_callback
        self.manual_stop_callback = manual_stop_callback
        self.model = model
        self.title("Настройки micPy")
        self.geometry("500x600")
        self.resizable(False, False)

        # Переменные состояния
        self.model_size = tk.StringVar(value=MODEL_SIZES[3])
        self.use_gpu = tk.BooleanVar(value=False)
        self.record_timeout = tk.IntVar(value=30)
        self.status = tk.StringVar(value="Ожидание")
        self.current_message = tk.StringVar(value="")
        self.history = []

        self.load_settings()
        self.create_widgets()
    def on_history_select(self, event):
        selection = self.history_listbox.curselection()
        if selection:
            index = selection[0]
            message = self.history_listbox.get(index)
            self.current_message.set(message)

    def create_widgets(self):
        # --- Кнопка для транскрипции файла ---
        frame_file = ttk.Frame(self)
        frame_file.pack(fill="x", padx=10, pady=5)
        file_btn = ttk.Button(frame_file, text="Выбрать файл для транскрипции", command=self.transcribe_file_dialog)
        file_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        # --- Настройки модели ---
        frame_settings = ttk.LabelFrame(self, text="Параметры модели")
        frame_settings.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame_settings, text="Размер модели:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        model_menu = ttk.Combobox(frame_settings, textvariable=self.model_size, values=MODEL_SIZES, state="readonly")
        model_menu.grid(row=0, column=1, padx=5, pady=5)

        gpu_check = ttk.Checkbutton(frame_settings, text="Использовать GPU", variable=self.use_gpu)
        gpu_check.grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(frame_settings, text="Длительность записи (сек):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        timeout_entry = ttk.Entry(frame_settings, textvariable=self.record_timeout, width=10)
        timeout_entry.grid(row=2, column=1, padx=5, pady=5)

        # --- Сервисные кнопки ---
        frame_service = ttk.Frame(self)
        frame_service.pack(fill="x", padx=10, pady=5)
        apply_btn = ttk.Button(frame_service, text="Применить", command=self.apply_settings)
        apply_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        save_btn = ttk.Button(frame_service, text="Сохранить", command=self.save_settings)
        save_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        # --- Статус и сообщения ---
        frame_status = ttk.LabelFrame(self, text="Статус и сообщения")
        frame_status.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame_status, text="Статус:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        status_label = ttk.Label(frame_status, textvariable=self.status, foreground="blue")
        status_label.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        # ttk.Label(frame_status, text="Текущее сообщение:").grid(row=1, column=0, sticky="nw", padx=5, pady=5)
        # current_msg_entry = ttk.Entry(frame_status, textvariable=self.current_message, state="readonly", width=50)
        # current_msg_entry.grid(row=1, column=1, padx=5, pady=5)

        # --- Кнопки ручного управления записью ---
        frame_manual = ttk.Frame(self)
        frame_manual.pack(fill="x", padx=10, pady=5)
        self.manual_start_btn = ttk.Button(frame_manual, text="Начать запись", command=self.start_manual_recording)
        self.manual_start_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        self.manual_stop_btn = ttk.Button(frame_manual, text="Остановить запись", command=self.stop_manual_recording)
        self.manual_stop_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)

        # --- История сообщений ---
        frame_history = ttk.LabelFrame(self, text="История сообщений")
        frame_history.pack(fill="both", expand=True, padx=10, pady=10)
        self.history_listbox = tk.Listbox(frame_history, height=8)
        self.history_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)
        
        # --- Копирование и справка ---
        frame_guide = ttk.Frame(self)
        frame_guide.pack(fill="x", padx=10, pady=5)
        copy_btn = ttk.Button(frame_guide, text="Копировать в буфер", command=self.copy_current_message)
        copy_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        guide_btn = ttk.Button(frame_guide, text="Краткое руководство", command=self.show_guide)
        guide_btn.pack(side="left", padx=5, pady=5, fill="x", expand=True)
        guide_btn.pack(side="right", padx=5)
        # --- Обработчик выбора и транскрипции файла ---
    def transcribe_file_dialog(self):
        filetypes = [
            ("Аудиофайлы", "*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus"),
            ("Все файлы", "*.*"),
        ]
        filepath = filedialog.askopenfilename(
            title="Выберите аудиофайл для транскрипции",
            filetypes=filetypes
        )
        if not filepath:
            return
        if not self.model:
            messagebox.showerror("Ошибка", "Модель не инициализирована.")
            return
        try:
            self.status.set("Транскрипция файла...")
            self.update()
            import pyperclip
            result = self.model.transcribe(filepath)
            text = result.get("text", "")
            self.current_message.set(text)
            self.history.append(text)
            self.history_listbox.insert("end", text)
            try:
                pyperclip.copy(text)
                messagebox.showinfo("Готово", "Текст скопирован в буфер обмена.")
            except Exception as e:
                messagebox.showwarning("Внимание", f"Не удалось скопировать в буфер обмена: {e}")
            self.status.set("Транскрипция завершена")
        except Exception as e:
            self.status.set("Ошибка транскрипции")
            messagebox.showerror("Ошибка транскрипции", str(e))

    def start_manual_recording(self):
        self.status.set("Ручная запись: идет...")
        if self.manual_start_callback:
            self.manual_start_callback()

    def stop_manual_recording(self):
        self.status.set("Ручная запись: остановлена")
        if self.manual_stop_callback:
            self.manual_stop_callback()
    def block_start_button(self):
        self.manual_start_btn.config(state="disabled")

    def unblock_start_button(self):
        self.manual_start_btn.config(state="normal")

    def block_stop_button(self):
        self.manual_stop_btn.config(state="disabled")

    def unblock_stop_button(self):
        self.manual_stop_btn.config(state="normal")

    def block_record_buttons(self):
        self.manual_start_btn.config(state="disabled")
        self.manual_stop_btn.config(state="disabled")

    def unblock_record_buttons(self):
        self.manual_start_btn.config(state="normal")
        self.manual_stop_btn.config(state="normal")

    def copy_current_message(self):
        msg = self.current_message.get()
        if msg:
            self.clipboard_clear()
            self.clipboard_append(msg)
            messagebox.showinfo("micPy", "Сообщение скопировано в буфер обмена.")

    def apply_settings(self):
        # Здесь будет логика применения настроек к основному приложению
        messagebox.showinfo("micPy", "Настройки применены.")

    def save_settings(self):
        data = {
            "model_size": self.model_size.get(),
            "use_gpu": self.use_gpu.get(),
            "record_timeout": self.record_timeout.get()
        }
        try:
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("micPy", "Настройки сохранены.")
        except Exception as e:
            messagebox.showerror("micPy", f"Ошибка сохранения настроек: {e}")

    def load_settings(self):
        if os.path.exists(self.SETTINGS_FILE):
            try:
                with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.model_size.set(data.get("model_size", MODEL_SIZES[3]))
                self.use_gpu.set(data.get("use_gpu", False))
                self.record_timeout.set(data.get("record_timeout", 30))
            except Exception as e:
                messagebox.showerror("micPy", f"Ошибка загрузки настроек: {e}")

    def show_guide(self):
        guide = (
            "Краткое руководство:\n"
            "- Выберите размер модели и длительность записи.\n"
            "- Включите GPU, если доступно.\n"
            "- Статус показывает текущее состояние.\n"
            "- История содержит последние сообщения.\n"
            "- Используйте кнопки для управления.\n" \
            "Нажмите Ctrl + PrtScr чтобы активировать или деактивировать запись.\n" \
            "Нажмите Ctrl + Ctrl + PrtScr чтобы завершить программу."
        )
        messagebox.showinfo("micPy - Руководство", guide)

    def add_to_history(self, message):
        self.history.append(message)
        self.history_listbox.insert(0, message)
        if len(self.history) > 20:
            self.history.pop()
            self.history_listbox.delete(20)

if __name__ == "__main__":
    app = SettingsWindow()
    app.mainloop()