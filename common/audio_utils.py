import base64
import io
import soundfile as sf
from typing import Tuple

def encode_audio_to_base64(audio_data: bytes, sample_rate: int, channels: int = 1) -> str:
    """Кодирует аудио данные в base64"""
    with io.BytesIO() as buffer:
        # Конвертируем raw audio в wav формат
        audio_array, _ = sf.read(io.BytesIO(audio_data), 
                                format='RAW',
                                samplerate=sample_rate, 
                                channels=channels,
                                subtype='PCM_16', 
                                dtype='float32')
        sf.write(buffer, audio_array, sample_rate, format='WAV')
        wav_data = buffer.getvalue()
    
    return base64.b64encode(wav_data).decode('utf-8')

def decode_base64_to_audio(base64_data: str) -> bytes:
    """Декодирует base64 в аудио данные"""
    return base64.b64decode(base64_data)

def save_base64_audio(base64_data: str, output_path: str) -> None:
    """Сохраняет base64 аудио в файл"""
    audio_data = decode_base64_to_audio(base64_data)
    with open(output_path, 'wb') as f:
        f.write(audio_data)