import fcntl
import sys

def check_single_instance(lock_file_path):
    """
    Проверить единственный экземпляр приложения.
    
    Returns:
        tuple: (instance_running, lock_file_or_None)
        - instance_running: True если это первый запуск, False если уже запущен
        - lock_file: объект файла блокировки (только для первого запуска)
    """
    try:
        # Открываем файл для блокировки
        lock_file = open(lock_file_path, 'w')
        # Пытаемся заблокировать файл
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Блокировка успешна - это первый запуск
        return True, lock_file
    except BlockingIOError:
        # Файл заблокирован - экземпляр уже запущен
        return False, None
