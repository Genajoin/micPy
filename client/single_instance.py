import fcntl
import sys

def check_single_instance(lock_file_path):
    # Открываем файл для блокировки
    lock_file = open(lock_file_path, 'w')
    try:
        # Пытаемся заблокировать файл
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True, lock_file
    except BlockingIOError:
        print("Another instance is already running.")
        sys.exit(1)
