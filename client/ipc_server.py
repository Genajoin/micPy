#!/usr/bin/env python3
import os
import signal
import socket
import threading
import tempfile
import getpass
import logging

log = logging.getLogger(__name__)

class IPCServer:
    """
    Unix Domain Socket сервер для межпроцессного взаимодействия.
    
    Команды:
    - START - начать запись
    - STOP - остановить запись
    - TOGGLE - переключить запись
    - QUIT - завершить приложение
    - STATUS - получить статус
    """
    
    def __init__(self, audio_recorder, timeout_duration=30):
        self.audio_recorder = audio_recorder
        self.timeout_duration = timeout_duration
        self.socket_path = os.path.join(
            tempfile.gettempdir(), 
            f"micpy-{getpass.getuser()}.sock"
        )
        self.server_socket = None
        self.running = False
        
    def start_server(self):
        """Запустить IPC сервер"""
        # Удаляем старый socket если существует
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
            
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(5)
        self.running = True
        
        log.info(f"IPC сервер запущен на {self.socket_path}")
        
        # Запускаем сервер в отдельном потоке
        threading.Thread(target=self._server_loop, daemon=True).start()
        
    def stop_server(self):
        """Остановить IPC сервер"""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
            
    def _server_loop(self):
        """Основной цикл сервера"""
        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                log.info("IPC: Новое подключение клиента")
                threading.Thread(
                    target=self._handle_client, 
                    args=(client_socket,), 
                    daemon=True
                ).start()
            except OSError:
                # Сокет закрыт
                log.info("IPC: Сервер остановлен")
                break
            except Exception as e:
                log.error(f"Ошибка в IPC сервере: {e}")
                
    def _handle_client(self, client_socket):
        """Обработать клиентское подключение"""
        try:
            data = client_socket.recv(1024).decode('utf-8').strip()
            log.info(f"IPC: Получена команда '{data}'")
            response = self._process_command(data)
            log.info(f"IPC: Отправка ответа '{response}'")
            client_socket.send(response.encode('utf-8'))
        except Exception as e:
            error_msg = f"Ошибка обработки IPC клиента: {e}"
            log.error(error_msg)
            try:
                client_socket.send(f"ERROR:{error_msg}".encode('utf-8'))
            except:
                pass
        finally:
            client_socket.close()
            log.info("IPC: Подключение клиента закрыто")
            
    def _process_command(self, command):
        """Обработать команду"""
        command = command.upper().strip()
        
        if command == "START":
            if not self.audio_recorder.recording_active:
                log.info("IPC: Выполнение START - начинаем запись")
                self.audio_recorder.start_recording(timeout=self.timeout_duration)
                return "OK:RECORDING_STARTED"
            else:
                log.info("IPC: START игнорируется - запись уже активна")
                return "ERROR:ALREADY_RECORDING"
                
        elif command == "STOP":
            if self.audio_recorder.recording_active:
                log.info("IPC: Выполнение STOP - останавливаем запись")
                self.audio_recorder.stop_recording()
                return "OK:RECORDING_STOPPED"
            else:
                log.info("IPC: STOP игнорируется - запись не активна")
                return "ERROR:NOT_RECORDING"
                
        elif command == "TOGGLE":
            if self.audio_recorder.recording_active:
                log.info("IPC: Выполнение TOGGLE - останавливаем запись")
                self.audio_recorder.stop_recording()
                return "OK:RECORDING_STOPPED"
            else:
                log.info("IPC: Выполнение TOGGLE - начинаем запись")
                self.audio_recorder.start_recording(timeout=self.timeout_duration)
                return "OK:RECORDING_STARTED"
                
        elif command == "STATUS":
            status = "RECORDING" if self.audio_recorder.recording_active else "IDLE"
            return f"OK:{status}"
            
        elif command == "QUIT":
            # Завершение приложения через сигнал
            threading.Timer(0.1, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
            return "OK:QUITTING"
            
        else:
            return f"ERROR:UNKNOWN_COMMAND:{command}"


def send_command(command):
    """
    Отправить команду работающему экземпляру micPy.
    
    Args:
        command (str): Команда для отправки
        
    Returns:
        str: Ответ от сервера или сообщение об ошибке
    """
    socket_path = os.path.join(
        tempfile.gettempdir(), 
        f"micpy-{getpass.getuser()}.sock"
    )
    
    if not os.path.exists(socket_path):
        return "ERROR:NO_INSTANCE_RUNNING"
        
    try:
        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_socket.connect(socket_path)
        client_socket.send(command.encode('utf-8'))
        
        response = client_socket.recv(1024).decode('utf-8')
        client_socket.close()
        return response
        
    except Exception as e:
        return f"ERROR:CONNECTION_FAILED:{e}"


if __name__ == "__main__":
    # Тест отправки команды
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        result = send_command(command)
        print(result)
    else:
        print("Использование: python ipc_server.py <команда>")
        print("Команды: START, STOP, TOGGLE, STATUS, QUIT")