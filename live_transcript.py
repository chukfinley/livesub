#!/usr/bin/env python3
"""
Live Transcription Overlay - Transcribes system audio in real-time using Groq Whisper.
Simple GTK-style UI with smart text fading.
"""

import os
import sys
import queue
import subprocess
import threading
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from dotenv import load_dotenv
from groq import Groq
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont


load_dotenv()

# Configuration
SAMPLE_RATE = 16000
CHUNK_DURATION = 3.0  # Longer chunks = less hallucination
WORD_FADE_MS = 3000  # Each word fades after 3 seconds
HISTORY_FILE = Path("transcript_history.txt")

# Known Whisper hallucinations to filter out
HALLUCINATION_FILTERS = [
    "vielen dank",
    "danke fürs zuschauen",
    "danke für's zuschauen",
    "bis zum nächsten mal",
    "untertitel von",
    "untertitel der",
    "subtitles by",
    "thank you for watching",
    "thanks for watching",
    "subscribe",
    "abonnieren",
    "amen",
    "amén",
]


def is_hallucination(text: str) -> bool:
    """Check if text is a known Whisper hallucination."""
    text_lower = text.lower().strip()
    if len(text_lower) < 3:
        return True
    for pattern in HALLUCINATION_FILTERS:
        if pattern in text_lower:
            return True
    return False


class TranscriptionSignals(QObject):
    new_text = pyqtSignal(str)
    error = pyqtSignal(str)


class AudioCapture:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self.audio_queue = queue.Queue()
        self.running = False
        self.process = None
        self.monitor_source = None
        self.read_thread = None

    def find_monitor_source(self) -> str | None:
        try:
            result = subprocess.run(
                ['pactl', 'list', 'sources', 'short'],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'monitor' in line.lower() and line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        return parts[1]
        except FileNotFoundError:
            pass
        return "@DEFAULT_MONITOR@"

    def read_audio_loop(self):
        chunk_bytes = int(self.sample_rate * 0.1) * 2
        while self.running and self.process and self.process.poll() is None:
            try:
                data = self.process.stdout.read(chunk_bytes)
                if data:
                    audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    self.audio_queue.put(audio)
            except Exception:
                pass

    def start(self):
        self.monitor_source = self.find_monitor_source()
        cmd = [
            'parec', '--device', self.monitor_source,
            '--format=s16le', '--rate', str(self.sample_rate),
            '--channels', '1', '--latency-msec=20'
        ]
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.running = True
        self.read_thread = threading.Thread(target=self.read_audio_loop, daemon=True)
        self.read_thread.start()

    def stop(self):
        self.running = False
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=2)

    def get_chunk(self, duration: float) -> np.ndarray | None:
        samples_needed = int(self.sample_rate * duration)
        collected = []
        collected_samples = 0
        while collected_samples < samples_needed and self.running:
            try:
                data = self.audio_queue.get(timeout=0.5)
                collected.append(data)
                collected_samples += len(data)
            except queue.Empty:
                if not self.running:
                    return None
        if not collected:
            return None
        return np.concatenate(collected, axis=0)[:samples_needed].flatten()


class GroqTranscriber:
    def __init__(self):
        api_key = os.getenv('GROQ')
        if not api_key:
            raise ValueError("GROQ API key not found")
        self.client = Groq(api_key=api_key)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        audio_int16 = (audio * 32767).astype(np.int16)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            temp_path = f.name
            wavfile.write(temp_path, sample_rate, audio_int16)
        try:
            with open(temp_path, 'rb') as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    file=(temp_path, audio_file.read()),
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language="de",
                )
            return transcription.strip() if transcription else ""
        finally:
            os.unlink(temp_path)


class TranscriptHistory:
    def __init__(self, filepath: Path = HISTORY_FILE):
        self.filepath = filepath
        with open(self.filepath, 'a', encoding='utf-8') as f:
            f.write(f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    def append(self, text: str):
        if text.strip():
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(f"{text}\n")


class TranscriptionOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signals = TranscriptionSignals()
        self.signals.new_text.connect(self.add_new_text)
        self.signals.error.connect(self.show_error)

        # Two lines of text
        self.line1 = ""  # older line (top)
        self.line2 = ""  # current line (bottom)
        self.line2_time = 0

        self.fade_timer = QTimer()
        self.fade_timer.timeout.connect(self.check_fade)
        self.fade_timer.start(100)

        self.history = TranscriptHistory()
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setStyleSheet("background-color: #000000;")

        central = QWidget()
        self.setCentralWidget(central)

        from PyQt6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        # Line 1 (top, older text, dimmer)
        self.label1 = QLabel("")
        self.label1.setFont(QFont("Sans", 16))
        self.label1.setStyleSheet("color: #888888;")
        self.label1.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label1)

        # Line 2 (bottom, current text, bright)
        self.label2 = QLabel("")
        self.label2.setFont(QFont("Sans", 18))
        self.label2.setStyleSheet("color: #FFFFFF;")
        self.label2.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label2)

        # Fixed size, position at bottom center
        screen = QApplication.primaryScreen().geometry()
        width = int(screen.width() * 0.65)
        height = 90
        x = (screen.width() - width) // 2
        y = screen.height() - height - 50
        self.setFixedSize(width, height)
        self.move(x, y)

        self.dragging = False
        self.drag_pos = None

    def add_new_text(self, text: str):
        if not text:
            return
        self.history.append(text)

        # Move current line2 to line1, new text becomes line2
        if self.line2:
            self.line1 = self.line2
        self.line2 = text
        self.line2_time = datetime.now().timestamp() * 1000
        self.update_display()

    def check_fade(self):
        """Fade out old text."""
        if not self.line2:
            return
        now = datetime.now().timestamp() * 1000
        age = now - self.line2_time

        # After WORD_FADE_MS, move line2 to line1 and clear
        if age > WORD_FADE_MS:
            if self.line2:
                self.line1 = self.line2
                self.line2 = ""
                self.line2_time = now
                self.update_display()

        # Clear line1 after another fade period
        if self.line1 and not self.line2 and age > WORD_FADE_MS * 0.5:
            self.line1 = ""
            self.update_display()

    def update_display(self):
        self.label1.setText(self.line1)
        self.label2.setText(self.line2)

    def show_error(self, error: str):
        self.label2.setText(f"Error: {error}")
        self.label2.setStyleSheet("color: #FF6666;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.dragging and self.drag_pos:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            QApplication.quit()
        elif event.key() == Qt.Key.Key_C:
            self.line1 = ""
            self.line2 = ""
            self.update_display()


class LiveTranscriptionApp:
    def __init__(self):
        self.audio_capture = AudioCapture()
        self.transcriber = GroqTranscriber()
        self.running = False

    def transcription_loop(self, signals: TranscriptionSignals):
        while self.running:
            try:
                audio = self.audio_capture.get_chunk(CHUNK_DURATION)
                if audio is None:
                    continue
                if np.abs(audio).max() < 0.02:
                    continue
                text = self.transcriber.transcribe(audio, SAMPLE_RATE)
                if text and not is_hallucination(text):
                    signals.new_text.emit(text)
            except Exception as e:
                signals.error.emit(str(e))

    def start(self, signals: TranscriptionSignals):
        self.audio_capture.start()
        self.running = True
        threading.Thread(target=self.transcription_loop, args=(signals,), daemon=True).start()

    def stop(self):
        self.running = False
        self.audio_capture.stop()


def main():
    print("Live Transcription - ESC to quit, C to clear")
    print(f"History: {HISTORY_FILE.absolute()}")

    app = QApplication(sys.argv)
    overlay = TranscriptionOverlay()
    overlay.show()

    transcription_app = LiveTranscriptionApp()
    try:
        transcription_app.start(overlay.signals)
    except Exception as e:
        overlay.signals.error.emit(str(e))

    app.aboutToQuit.connect(transcription_app.stop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
