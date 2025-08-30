#!/usr/bin/env python3
import os
import signal
import logging
from gi.repository import GLib
import pydbus
from pydbus import SystemBus

log = logging.getLogger(__name__)

class MicPyRecorderService:
    """
    D-Bus сервис для управления записью через системные горячие клавиши.
    
    Интерфейс: com.micpy.Recorder
    Методы:
    - StartRecording() - начать запись
    - StopRecording() - остановить запись  
    - ToggleRecording() - переключить запись
    - Quit() - завершить приложение
    - GetStatus() -> строка статуса
    """
    
    dbus = """
    <node>
        <interface name='com.micpy.Recorder'>
            <method name='StartRecording'/>
            <method name='StopRecording'/>
            <method name='ToggleRecording'/>
            <method name='Quit'/>
            <method name='GetStatus'>
                <arg type='s' name='status' direction='out'/>
            </method>
            <signal name='StatusChanged'>
                <arg type='s' name='status'/>
            </signal>
        </interface>
    </node>
    """
    
    def __init__(self, audio_recorder):
        self.audio_recorder = audio_recorder
        self.bus = pydbus.SessionBus()
        self.loop = None
        
    def StartRecording(self):
        """Начать запись с таймаутом"""
        log.info("D-Bus: StartRecording")
        if not self.audio_recorder.recording_active:
            self.audio_recorder.start_recording(timeout=self.audio_recorder.timeout_duration)
        
    def StopRecording(self):
        """Остановить запись"""
        log.info("D-Bus: StopRecording")
        if self.audio_recorder.recording_active:
            self.audio_recorder.stop_recording()
            
    def ToggleRecording(self):
        """Переключить состояние записи"""
        log.info("D-Bus: ToggleRecording")
        if self.audio_recorder.recording_active:
            self.audio_recorder.stop_recording()
        else:
            self.audio_recorder.start_recording(timeout=self.audio_recorder.timeout_duration)
            
    def GetStatus(self):
        """Получить текущий статус"""
        status = "Recording" if self.audio_recorder.recording_active else "Idle"
        return status
        
    def Quit(self):
        """Завершить приложение"""
        log.info("D-Bus: Quit")
        if self.loop:
            self.loop.quit()
        os.kill(os.getpid(), signal.SIGTERM)
        
    def StatusChanged(self, status):
        """Сигнал об изменении статуса"""
        pass  # Будет автоматически отправляться
        
    def start_service(self):
        """Запустить D-Bus сервис"""
        try:
            self.bus.publish("com.micpy.Recorder", self)
            log.info("D-Bus сервис com.micpy.Recorder зарегистрирован")
            
            self.loop = GLib.MainLoop()
            
            def handle_signal(signum, frame):
                log.info("Получен сигнал завершения D-Bus сервиса")
                self.loop.quit()
                
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            
            log.info("D-Bus сервис запущен, ожидание команд...")
            self.loop.run()
            
        except Exception as e:
            log.error(f"Ошибка запуска D-Bus сервиса: {e}")
            
    def emit_status_changed(self, status):
        """Отправить сигнал об изменении статуса"""
        try:
            self.StatusChanged(status)
        except Exception as e:
            log.error(f"Ошибка отправки D-Bus сигнала: {e}")