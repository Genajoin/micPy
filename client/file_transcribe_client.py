#!/usr/bin/env python3
"""
Клиент для отправки аудио файлов на транскрипцию через HTTP API.
Простая утилита командной строки для быстрой транскрипции MP3/WAV файлов.
"""

import os
import sys
import argparse
import requests
from pathlib import Path
from typing import Optional

def transcribe_file(
    file_path: str,
    server_url: str = "http://localhost:8013",
    output_file: Optional[str] = None,
    beam_size: int = 5,
    language: Optional[str] = None,
    include_segments: bool = False,
    vad_filter: bool = False,
    verbose: bool = True
) -> dict:
    """
    Отправка аудио файла на транскрипцию.
    
    Args:
        file_path: Путь к аудио файлу
        server_url: URL сервера (default: http://genaminipc.awg:8013)
        output_file: Путь для сохранения текста (опционально)
        beam_size: Размер beam search (1-10, выше = лучше качество)
        language: Язык аудио (ru, en, auto, ...)
        include_segments: Включить временные метки в результат
        verbose: Выводить подробную информацию
        
    Returns:
        Словарь с результатами транскрипции
    """
    # Проверяем существование файла
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    if verbose:
        print(f"📁 Файл: {file_path}")
        print(f"📊 Размер: {file_size_mb:.2f} MB")
        print(f"🌐 Сервер: {server_url}")
        print(f"⚙️  Параметры: beam_size={beam_size}, language={language or 'auto'}")
        print(f"📤 Отправка файла на транскрипцию...")
    
    # Подготавливаем данные для отправки
    with open(file_path, 'rb') as f:
        files = {'file': (os.path.basename(file_path), f)}
        
        # Формируем параметры
        data = {
            'beam_size': str(beam_size),
            'include_segments': 'true' if include_segments else 'false',
            'vad_filter': 'true' if vad_filter else 'false'
        }
        
        if language:
            data['language'] = language
        
        response = None
        try:
            # Отправляем запрос
            response = requests.post(
                f"{server_url}/transcribe",
                files=files,
                data=data,
                timeout=600  # 10 минут таймаут для больших файлов
            )
            
            # Проверяем статус ответа
            response.raise_for_status()
            
            # Парсим результат
            result = response.json()
            
            if verbose:
                print(f"✅ Транскрипция завершена!")
                print(f"🌍 Язык: {result.get('language', 'unknown')}")
                print(f"⏱️  Длительность: {result.get('duration', 0):.2f} сек")
                print(f"📝 Текст ({len(result.get('text', ''))} символов):")
                print("-" * 60)
                print(result.get('text', ''))
                print("-" * 60)
            
            # Сохраняем в файл если указан
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as out:
                    out.write(result.get('text', ''))
                    
                    # Добавляем сегменты если есть
                    if 'segments' in result:
                        out.write('\n\n--- Временные метки ---\n')
                        for seg in result['segments']:
                            out.write(f"[{seg['start']:.2f}s - {seg['end']:.2f}s] {seg['text']}\n")
                
                if verbose:
                    print(f"💾 Результат сохранен в: {output_file}")
            
            return result
            
        except requests.exceptions.Timeout:
            print("❌ Ошибка: Превышено время ожидания ответа от сервера")
            raise
        except requests.exceptions.ConnectionError:
            print(f"❌ Ошибка: Не удалось подключиться к серверу {server_url}")
            print("   Убедитесь что сервер запущен и доступен")
            raise
        except requests.exceptions.HTTPError as e:
            print(f"❌ Ошибка HTTP: {e}")
            if response and response.text:
                try:
                    error_data = response.json()
                    print(f"   Сообщение: {error_data.get('error', 'Неизвестная ошибка')}")
                except:
                    print(f"   Ответ: {response.text}")
            raise
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            raise

def main():
    """Главная функция командной строки."""
    parser = argparse.ArgumentParser(
        description='Транскрипция аудио файлов через STT сервер',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Простая транскрипция
  python3 file_transcribe_client.py audio.mp3
  
  # Сохранить результат в файл
  python3 file_transcribe_client.py audio.mp3 -o transcript.txt
  
  # Указать язык и параметры качества
  python3 file_transcribe_client.py audio.mp3 -l ru -b 10
  
  # Включить временные метки
  python3 file_transcribe_client.py audio.mp3 --segments -o transcript.txt
  
  # Указать другой сервер
  python3 file_transcribe_client.py audio.mp3 -s http://localhost:8013

Поддерживаемые форматы: MP3, WAV, M4A, FLAC, OGG, OPUS
        """
    )
    
    parser.add_argument('file', help='Путь к аудио файлу')
    parser.add_argument('-o', '--output', help='Файл для сохранения результата')
    parser.add_argument('-s', '--server', default='http://localhost:8013',
                       help='URL сервера (default: http://localhost:8013)')
    parser.add_argument('-b', '--beam-size', type=int, default=5,
                       help='Размер beam search (1-10, default: 5)')
    parser.add_argument('-l', '--language',
                       help='Язык аудио (ru, en, auto, ...)')
    parser.add_argument('--segments', action='store_true',
                       help='Включить временные метки в результат')
    parser.add_argument('--vad', action='store_true',
                       help='Включить VAD фильтр для удаления тишины')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Минимальный вывод (только текст)')
    
    args = parser.parse_args()
    
    try:
        # Выполняем транскрипцию
        result = transcribe_file(
            file_path=args.file,
            server_url=args.server,
            output_file=args.output,
            beam_size=args.beam_size,
            language=args.language,
            include_segments=args.segments,
            vad_filter=args.vad,
            verbose=not args.quiet
        )
        
        # В quiet режиме выводим только текст
        if args.quiet:
            print(result.get('text', ''))
        
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        if not args.quiet:
            print(f"\n❌ Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
