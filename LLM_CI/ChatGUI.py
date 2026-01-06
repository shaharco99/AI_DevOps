from __future__ import annotations

import os
import sys
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget
)

# -----------------------------------------------------------------------------
# Mock Utils (Replace with your actual Utils.py imports)
# -----------------------------------------------------------------------------
try:
    from Utils import get_llm_provider, process_prompt, reset_chat_usage_log, system_message
except ImportError:
    def get_llm_provider():
        return None

    def process_prompt(prompt, llm, verbose, usage_mode):
        return f"Echo: {prompt}"

    def reset_chat_usage_log():
        pass

    system_message = 'You are a helpful DevOps assistant.'

# -----------------------------------------------------------------------------
# WORKER THREAD
# -----------------------------------------------------------------------------


class Worker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    thinking_started = pyqtSignal()
    thinking_stopped = pyqtSignal()

    def __init__(self, prompt: str, llm, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.llm = llm

    def run(self):
        try:
            self.thinking_started.emit()
            response = process_prompt(self.prompt, self.llm, verbose=False, usage_mode='chat')
            self.thinking_stopped.emit()
            self.finished.emit(response)
        except Exception as exc:
            self.thinking_stopped.emit()
            self.error.emit(str(exc))

# -----------------------------------------------------------------------------
# UI COMPONENT: Typing Indicator
# -----------------------------------------------------------------------------


class TypingIndicator(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)

        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 8)
        self.layout.setSpacing(4)

        # Typing Label
        self.label = QLabel("...")
        self.label.setFont(QFont('Segoe UI', 10))
        self.layout.addWidget(self.label)

        # Animation timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.dot_count = 1
        self.timer.start(500)  # Update every 500ms

        # Styling
        self.setStyleSheet("""
            TypingIndicator {
                background-color: #ffffff;
                border-radius: 15px 15px 15px 0px;
            }
            QLabel {
                background-color: transparent;
                border: none;
                color: #888;
            }
        """)

    def animate(self):
        """Animate the dots"""
        self.dot_count = (self.dot_count % 3) + 1
        self.label.setText("•" * self.dot_count)

    def stop_animation(self):
        """Stop the animation timer"""
        self.timer.stop()

    def __del__(self):
        """Clean up timer"""
        if self.timer.isActive():
            self.timer.stop()


# -----------------------------------------------------------------------------
# UI COMPONENT: Message Bubble
# -----------------------------------------------------------------------------


class MessageBubble(QFrame):
    def __init__(self, message: str, is_user: bool, timestamp: str, date_tooltip: str = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)

        # 1. Main Layout inside the bubble
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 8)
        self.layout.setSpacing(4)

        # 2. Text Label
        self.text_label = QLabel(message)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_label.setOpenExternalLinks(True)

        # Font Logic
        font = QFont('Segoe UI', 10)
        if '```' in message:
            font = QFont('Consolas', 10)
            self.text_label.setStyleSheet('color: #333;')
        self.text_label.setFont(font)

        # 3. Timestamp Label
        self.time_label = QLabel(timestamp)
        self.time_label.setFont(QFont('Segoe UI', 8))
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        # Set the Date Tooltip
        if date_tooltip:
            self.time_label.setToolTip(date_tooltip)

        ts_color = '#9dbd9e' if is_user else '#8faeb5'
        self.time_label.setStyleSheet(f"color: {ts_color}; background: transparent;")

        # Add to layout
        self.layout.addWidget(self.text_label)
        self.layout.addWidget(self.time_label)

        # 4. Styling (Borders & Colors)
        if is_user:
            bg = '#d9fdd3'  # WhatsApp Green
            # Top-Left, Top-Right, Bottom-Right (Sharp), Bottom-Left
            radius = '15px 15px 0px 15px'
        else:
            bg = '#ffffff'  # WhatsApp White
            # Top-Left, Top-Right, Bottom-Right, Bottom-Left (Sharp)
            radius = '15px 15px 15px 0px'

        self.setStyleSheet(f"""
            MessageBubble {{
                background-color: {bg};
                border-radius: {radius};
            }}
            QLabel {{
                background-color: transparent;
                border: none;
            }}
            /* Optional: Make tooltip look nice */
            QToolTip {{
                background-color: #333;
                color: white;
                border: 1px solid #333;
            }}
        """)

# -----------------------------------------------------------------------------
# UI COMPONENT: Message Row
# -----------------------------------------------------------------------------


class MessageRow(QWidget):
    def __init__(self, message: str, is_user: bool, timestamp: str, date_tooltip: str = None, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 4, 0, 4)
        self.layout.setSpacing(0)

        # Pass date_tooltip down to bubble
        self.bubble = MessageBubble(message, is_user, timestamp, date_tooltip)

        # Use 'Expanding' to encourage length over line breaks
        self.bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        if is_user:
            self.layout.addStretch()
            self.layout.addWidget(self.bubble)
        else:
            self.layout.addWidget(self.bubble)
            self.layout.addStretch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            # Width limit 85%
            max_width = int(self.parent().width() * 0.85)
            self.bubble.setMaximumWidth(max_width)

# -----------------------------------------------------------------------------
# MAIN WINDOW
# -----------------------------------------------------------------------------


class ChatWindow(QMainWindow):
    def __init__(self, llm):
        super().__init__()
        self.llm = llm
        self.typing_indicator = None
        self.typing_row = None
        self.setWindowTitle('MCP — DevOps Chat')
        self.resize(500, 750)

        # Global Styles
        self.setStyleSheet("""
            QMainWindow { background-color: #efe7dd; }
            QWidget#chat_container { background-color: #efe7dd; }
            QScrollArea { border: none; background: #efe7dd; }
            QLineEdit {
                border: none; border-radius: 20px;
                padding: 10px 15px; background: white; font-size: 14px;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        # 1. Header
        header = QFrame()
        header.setStyleSheet('background-color: #008069;')
        header.setFixedHeight(60)
        h_layout = QHBoxLayout(header)
        title = QLabel('💬 DevOps Assistant')
        title.setStyleSheet('color: white; font-weight: bold; font-size: 16px;')
        h_layout.addWidget(title)
        main_vbox.addWidget(header)

        # 2. Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.chat_container = QWidget()
        self.chat_container.setObjectName('chat_container')

        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(15, 15, 15, 15)
        self.chat_layout.setSpacing(5)
        self.chat_layout.addStretch()

        self.scroll.setWidget(self.chat_container)
        main_vbox.addWidget(self.scroll)

        # 3. Input Area
        input_frame = QFrame()
        input_frame.setStyleSheet('background-color: #f0f0f0;')
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(10, 8, 10, 8)

        self.upload_btn = QPushButton('📎')
        self.upload_btn.setFixedSize(40, 40)
        self.upload_btn.setFlat(True)
        self.upload_btn.clicked.connect(self.on_upload_file)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText('Type a message...')
        self.input_field.returnPressed.connect(self.on_send)

        self.send_btn = QPushButton('➤')
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.setStyleSheet("""
            QPushButton { background: #008069; color: white; border-radius: 20px; font-weight: bold;}
            QPushButton:hover { background: #006b58; }
        """)
        self.send_btn.clicked.connect(self.on_send)

        input_layout.addWidget(self.upload_btn)
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        main_vbox.addWidget(input_frame)

        # 4. Initialize System
        reset_chat_usage_log()
        self.add_chat_bubble(system_message, is_user=False)

    # -------------------------------------------------------------------------
    # UNIFIED MESSAGE SYSTEM
    # -------------------------------------------------------------------------
    def add_chat_bubble(self, text: str, is_user: bool):
        now = datetime.now()
        ts = now.strftime('%H:%M')
        # Full date for the tooltip (e.g. "Tuesday, November 25, 2025")
        dt_tooltip = now.strftime('%A, %B %d, %Y')

        row = MessageRow(text, is_user, ts, dt_tooltip, parent=self.chat_container)
        self.chat_layout.addWidget(row)
        QApplication.processEvents()
        # Use timer to ensure scroll happens after layout is fully rendered
        QTimer.singleShot(10, self.scroll_to_bottom)

    def show_typing_indicator(self):
        """Show the typing indicator animation"""
        self.typing_indicator = TypingIndicator(parent=self.chat_container)
        self.typing_row = QHBoxLayout()
        self.typing_row.setContentsMargins(0, 4, 0, 4)
        self.typing_row.setSpacing(0)
        self.typing_row.addWidget(self.typing_indicator)
        self.typing_row.addStretch()

        # Create a container widget for the layout
        container = QWidget()
        container.setLayout(self.typing_row)
        self.chat_layout.addWidget(container)
        QApplication.processEvents()
        # Use timer to ensure scroll happens after layout is fully rendered
        QTimer.singleShot(10, self.scroll_to_bottom)

    def hide_typing_indicator(self):
        """Hide and remove the typing indicator"""
        if self.typing_indicator:
            self.typing_indicator.stop_animation()
            # Remove the typing indicator widget
            widget = self.typing_indicator.parent()
            if widget:
                self.chat_layout.removeWidget(widget)
                widget.deleteLater()
            self.typing_indicator = None
            self.typing_row = None
            QApplication.processEvents()
            # Use timer to ensure scroll happens after layout is fully rendered
            QTimer.singleShot(10, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        scrollbar = self.scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # -------------------------------------------------------------------------
    # EVENT HANDLERS
    # -------------------------------------------------------------------------
    def on_send(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.add_chat_bubble(text, is_user=True)
        self.input_field.clear()
        self.input_field.setDisabled(True)
        self.send_btn.setDisabled(True)

        # Show typing indicator
        self.show_typing_indicator()

        self.worker = Worker(text, self.llm)
        self.worker.thinking_started.connect(self.on_thinking_started)
        self.worker.thinking_stopped.connect(self.on_thinking_stopped)
        self.worker.finished.connect(self.on_response)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_thinking_started(self):
        """Called when the agent starts processing"""
        pass  # Typing indicator is already shown

    def on_thinking_stopped(self):
        """Called when the agent finishes processing"""
        pass  # Will be hidden in on_response or on_error

    def on_response(self, response: str):
        self.hide_typing_indicator()
        self.add_chat_bubble(response, is_user=False)
        self.input_field.setDisabled(False)
        self.send_btn.setDisabled(False)
        self.input_field.setFocus()

    def on_error(self, err: str):
        self.hide_typing_indicator()
        self.add_chat_bubble(f"Error: {err}", is_user=False)
        self.input_field.setDisabled(False)
        self.send_btn.setDisabled(False)

    def on_upload_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select File')
        if file_path:
            filename = os.path.basename(file_path)
            self.add_chat_bubble(f"📎 Uploaded: {filename}", is_user=True)
            self.input_field.setText(f"Analyze the file {filename}...")
            self.input_field.setFocus()

# -----------------------------------------------------------------------------
# APP ENTRY
# -----------------------------------------------------------------------------


def run_gui():
    app = QApplication(sys.argv)
    font = QFont('Segoe UI', 9)
    app.setFont(font)

    llm = get_llm_provider()
    window = ChatWindow(llm)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
