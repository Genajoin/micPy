#!/usr/bin/env python3
import subprocess
import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

class TextInserter:
    """
    Универсальный класс для вставки текста в активное окно.
    
    Поддерживает несколько методов:
    1. xdotool - прямая вставка текста (лучший для X11)
    2. pynput - эмуляция клавиш
    3. clipboard_only - только копирование в буфер
    """
    
    def __init__(self, method="auto", keyboard_controller=None, keyboard_key=None):
        """
        Args:
            method: "auto", "xdotool", "pynput", "clipboard_only"
            keyboard_controller: pynput Controller (если доступен)
            keyboard_key: pynput Key класс (если доступен)
        """
        self.method = method
        self.keyboard_controller = keyboard_controller
        self.Key = keyboard_key
        self.available_methods = self._detect_available_methods()
        
        if method == "auto":
            self.selected_method = self._choose_best_method()
        else:
            self.selected_method = method if method in self.available_methods else "clipboard_only"
            
        log.info(f"TextInserter: использую метод '{self.selected_method}'")
    
    def _detect_available_methods(self):
        """Определить доступные методы вставки"""
        methods = ["clipboard_only"]  # Всегда доступен
        
        # ydotool требует специальной настройки в Wayland, пропускаем
            
        # Проверка pynput
        if self.keyboard_controller and self.Key:
            methods.append("pynput")
            
        log.info(f"Доступные методы вставки: {methods}")
        return methods
    
    def _check_command(self, command):
        """Проверить доступность команды"""
        try:
            subprocess.run([command, "--version"], 
                         capture_output=True, check=True, timeout=2)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _choose_best_method(self):
        """Выбрать лучший доступный метод"""
        # Приоритет методов (pynput в качестве основного)
        priority = ["pynput", "clipboard_only"]
        
        for method in priority:
            if method in self.available_methods:
                return method
        
        return "clipboard_only"
    
    # _get_active_window_class удален вместе с xdotool
    
    def insert_text(self, text):
        """
        Вставить текст в активное окно.
        
        Args:
            text: текст для вставки
            
        Returns:
            tuple: (success, method_used, message)
        """
        if not text:
            return False, "none", "Пустой текст"
            
        # Всегда копируем в буфер обмена
        try:
            import pyperclip
            pyperclip.copy(text)
            log.info("Текст скопирован в буфер обмена")
        except Exception as e:
            log.warning(f"Не удалось скопировать в буфер: {e}")
        
        if self.selected_method == "clipboard_only":
            return True, "clipboard_only", "Текст скопирован в буфер обмена"
            
        # ydotool пропущен из-за сложности настройки
            
        elif self.selected_method == "pynput":
            return self._insert_with_pynput(text)
            
        else:
            return True, "clipboard_only", "Метод недоступен, текст в буфере"
    
    # ydotool метод удален из-за сложности настройки в Wayland
    
    def _insert_with_pynput(self, text):
        """Вставка через pynput (резерв для X11)"""
        if not self.keyboard_controller or not self.Key:
            return False, "pynput_unavailable", "pynput недоступен"
            
        try:
            # Улучшенная вставка для лучшей совместимости
            log.info("pynput: используем Ctrl+V с задержками")
            time.sleep(0.3)  # Увеличенная задержка
            
            # Используем контекстный менеджер для надежности
            with self.keyboard_controller.pressed(self.Key.ctrl):
                time.sleep(0.1)
                self.keyboard_controller.press('v')
                time.sleep(0.1)
                self.keyboard_controller.release('v')
            
            return True, "pynput_improved", "Вставлено через улучшенный pynput"
                
        except Exception as e:
            log.warning(f"Ошибка pynput: {e}")
            return False, "pynput_failed", f"Ошибка pynput: {e}"


def create_text_inserter(method="auto", keyboard_controller=None, keyboard_key=None):
    """
    Фабричная функция для создания TextInserter.
    
    Args:
        method: "auto", "xdotool", "pynput", "clipboard_only"
        keyboard_controller: pynput Controller
        keyboard_key: pynput Key класс
        
    Returns:
        TextInserter: настроенный инстанс
    """
    return TextInserter(method, keyboard_controller, keyboard_key)


if __name__ == "__main__":
    # Тестирование
    import sys
    
    if len(sys.argv) > 1:
        test_text = " ".join(sys.argv[1:])
        
        inserter = create_text_inserter("auto")
        success, method, message = inserter.insert_text(test_text)
        
        print(f"Результат: {success}")
        print(f"Метод: {method}")
        print(f"Сообщение: {message}")
    else:
        print("Использование: python text_inserter.py <текст для вставки>")
        print("Доступные методы:", TextInserter("auto", None, None).available_methods)