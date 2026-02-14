from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

import markdown
import logging
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject
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
    QWidget,
)

# -----------------------------------------------------------------------------
# Imports for agent-driven functionality
# -----------------------------------------------------------------------------
try:
    # System message for initializing chat context
    from Utils import system_message
except ImportError:
    system_message = "You are a helpful DevOps assistant."

try:
    from Tools import get_vault_count
    from Utils import _load_vault_embedding_cache
except Exception:
    def get_vault_count(vp=None):
        return 0
    def _load_vault_embedding_cache(vp=None):
        return None, []

# -----------------------------------------------------------------------------
# WORKER THREAD (REFACTORED FOR UNIFIED AGENT)
# -----------------------------------------------------------------------------
class Worker(QThread):
    """
    Worker thread that runs the UnifiedAgent with a user's prompt.
    """
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt: str, agent, runner=None, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.agent = agent
        self.runner = runner

    def run(self):
        """
        Execute the agent's run method and emit the result.
        """
        try:
            if not self.agent:
                self.error.emit("UnifiedAgent not initialized.")
                return

            # Prefer shared AsyncRunner when available to avoid creating/closing loops
            if getattr(self, 'runner', None):
                try:
                    result = self.runner.run(self.agent.run(self.prompt))
                except Exception as e:
                    # Fall back to thread-local asyncio.run
                    result = asyncio.run(self.agent.run(self.prompt))
            else:
                # asyncio.run() creates a new event loop for the thread
                result = asyncio.run(self.agent.run(self.prompt))

            if result.get('status') == 'success':
                self.finished.emit(result.get('result', ''))
            else:
                error_msg = result.get('error', 'Agent returned an error.')
                self.error.emit(error_msg)

        except Exception as e:
            self.error.emit(f"An exception occurred: {e}")

# -----------------------------------------------------------------------------
# UI COMPONENT: Typing Indicator
# -----------------------------------------------------------------------------
class TypingIndicator(QFrame):
    def __init__(self, parent=None, initial_text: str | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 8)
        self.layout.setSpacing(4)
        self.label = QLabel(initial_text or '...')
        self.label.setFont(QFont('Segoe UI', 10))
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.dot_count = 1
        # Start animation only if no initial_text provided
        if initial_text is None:
            self.timer.start(500)
        self.setStyleSheet("""
            TypingIndicator { background-color: #ffffff; border-radius: 15px 15px 15px 0px; }
            QLabel { background-color: transparent; border: none; color: #888; }
        """)

    def animate(self):
        self.dot_count = (self.dot_count % 3) + 1
        self.label.setText('•' * self.dot_count)

    def stop_animation(self):
        self.timer.stop()

    def update_text(self, text: str):
        """Update the indicator with a message (stop dot animation)."""
        if self.timer.isActive():
            self.timer.stop()
        self.label.setText(text)

# -----------------------------------------------------------------------------
# UI COMPONENT: Message Bubble
# -----------------------------------------------------------------------------
class MessageBubble(QFrame):
    def __init__(self, message: str, is_user: bool, timestamp: str, date_tooltip: str = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 8)
        self.layout.setSpacing(4)

        html_message = markdown.markdown(message, extensions=['fenced_code', 'codehilite', 'tables', 'nl2br'])

        self.text_browser = QLabel()
        self.text_browser.setTextFormat(Qt.TextFormat.RichText)
        self.text_browser.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setWordWrap(True)
        self.text_browser.setText(html_message)
        font = QFont('Segoe UI'); font.setPixelSize(13)
        self.text_browser.setFont(font)
        self.text_browser.setStyleSheet('border: none; background: transparent; padding: 8px;')
        self.layout.addWidget(self.text_browser)
        self.text_browser.setObjectName('message_label')

        self.time_label = QLabel(timestamp)
        self.time_label.setFont(QFont('Segoe UI', 8))
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        if date_tooltip: self.time_label.setToolTip(date_tooltip)
        self.layout.addWidget(self.time_label)

        bg = '#e6fff2' if is_user else '#f7f9fb'
        text_color = '#002b20' if is_user else '#07121a'
        self.setStyleSheet(f"""
            MessageBubble {{ background-color: {bg}; border-radius: 8px; margin: 6px 0px; }}
            QLabel#message_label {{ color: {text_color}; background: transparent; }}
            QLabel#timestamp_label {{ color: #777777; background: transparent; }}
        """)
        self.time_label.setObjectName('timestamp_label')

# -----------------------------------------------------------------------------
# UI COMPONENT: Message Row
# -----------------------------------------------------------------------------
class MessageRow(QWidget):
    def __init__(self, message: str, is_user: bool, timestamp: str, date_tooltip: str = None, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 4, 6, 4)
        self.layout.setSpacing(2)
        self.bubble = MessageBubble(message, is_user, timestamp, date_tooltip)
        self.bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout.addWidget(self.bubble)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parent():
            max_width = int(self.parent().width() * 0.85)
            self.bubble.setMaximumWidth(max_width)


# -----------------------------------------------------------------------------
# Qt-friendly logging emitter and handler
# -----------------------------------------------------------------------------
class LogEmitter(QObject):
    message = pyqtSignal(str)


class QtLogHandler(logging.Handler):
    """Logging handler that emits records to a Qt signal for GUI display."""
    def __init__(self, emitter: LogEmitter):
        super().__init__()
        self.emitter = emitter
        fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.setFormatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Only forward messages from unified_agent logger
            if 'unified_agent' in (record.name or '') and record.levelno >= logging.INFO:
                msg = self.format(record)
                # Emit via Qt signal to ensure thread-safety
                self.emitter.message.emit(msg)
        except Exception:
            self.handleError(record)

# -----------------------------------------------------------------------------
# MAIN WINDOW (REFACTORED FOR UNIFIED AGENT)
# -----------------------------------------------------------------------------
class ChatWindow(QMainWindow):
    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.typing_indicator = None
        # Set up Qt log emitter and handler for unified_agent logs
        try:
            self._log_emitter = LogEmitter()
            self._log_emitter.message.connect(self.on_log_message)
            handler = QtLogHandler(self._log_emitter)
            handler.setLevel(logging.INFO)
            ua_logger = logging.getLogger('unified_agent')
            ua_logger.setLevel(logging.INFO)
            ua_logger.addHandler(handler)
        except Exception:
            # Non-fatal: logging integration is best-effort
            pass
        self.setWindowTitle('MCP — DevOps Unified Agent Chat')
        self.resize(800, 900)

        self.setStyleSheet("""
            QMainWindow { background-color: #efe7dd; }
            QWidget#chat_container { background-color: #efe7dd; }
            QScrollArea { border: none; background: #efe7dd; }
            QLineEdit { border: none; border-radius: 20px; padding: 10px 15px; background: white; font-size: 14px; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_vbox = QVBoxLayout(central)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.setSpacing(0)

        header = QFrame(); header.setStyleSheet('background-color: #008069;'); header.setFixedHeight(60)
        h_layout = QHBoxLayout(header)
        title = QLabel('💬 DevOps Assistant (Unified Agent)'); title.setStyleSheet('color: white; font-weight: bold; font-size: 16px;')
        h_layout.addWidget(title); h_layout.addStretch()
        self.doc_count_label = QLabel('Docs: 0'); self.doc_count_label.setStyleSheet('color: white; font-size: 12px;')
        self.cache_label = QLabel('Cache: none'); self.cache_label.setStyleSheet('color: white; font-size: 12px;')
        info_layout = QVBoxLayout(); info_layout.setContentsMargins(0, 6, 12, 6)
        info_layout.addWidget(self.doc_count_label); info_layout.addWidget(self.cache_label)
        info_widget = QWidget(); info_widget.setLayout(info_layout); h_layout.addWidget(info_widget)
        main_vbox.addWidget(header)

        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_container = QWidget(); self.chat_container.setObjectName('chat_container')
        self.chat_layout = QVBoxLayout(self.chat_container); self.chat_layout.setContentsMargins(15, 15, 15, 15); self.chat_layout.setSpacing(5); self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_container)
        main_vbox.addWidget(self.scroll)

        input_frame = QFrame(); input_frame.setStyleSheet('background-color: #f0f0f0;')
        input_layout = QHBoxLayout(input_frame); input_layout.setContentsMargins(10, 8, 10, 8)
        self.upload_btn = QPushButton('📎'); self.upload_btn.setFixedSize(40, 40); self.upload_btn.setFlat(True); self.upload_btn.clicked.connect(self.on_upload_file)
        self.input_field = QLineEdit(); self.input_field.setPlaceholderText('Ask the agent...'); self.input_field.returnPressed.connect(self.on_send)
        self.send_btn = QPushButton('➤'); self.send_btn.setFixedSize(40, 40)
        self.send_btn.setStyleSheet("""
            QPushButton { background: #008069; color: white; border-radius: 20px; font-weight: bold;}
            QPushButton:hover { background: #006b58; }
        """)
        self.send_btn.clicked.connect(self.on_send)
        input_layout.addWidget(self.upload_btn); input_layout.addWidget(self.input_field); input_layout.addWidget(self.send_btn)
        main_vbox.addWidget(input_frame)

        self.add_chat_bubble(system_message, is_user=False)
        self.update_vault_info()

    def update_vault_info(self):
        try: count = get_vault_count()
        except Exception: count = 0
        try: emb, lines = _load_vault_embedding_cache()
        except Exception: emb, lines = None, []
        self.doc_count_label.setText(f"Docs: {count}")
        if emb is not None:
            try: dim = int(emb.shape[1]) if hasattr(emb, 'shape') and len(emb.shape) > 1 else 0
            except Exception: dim = 0
            self.cache_label.setText(f"Cache: {len(lines)} × {dim}d")
        else: self.cache_label.setText('Cache: none')

    def add_chat_bubble(self, text: str, is_user: bool):
        now = datetime.now()
        ts = now.strftime('%H:%M'); dt_tooltip = now.strftime('%A, %B %d, %Y')
        row = MessageRow(text, is_user, ts, dt_tooltip, parent=self.chat_container)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        QTimer.singleShot(10, self.scroll_to_bottom)
        QApplication.processEvents()

    def show_typing_indicator(self, message: str | None = None):
        """Show typing indicator. If `message` provided, display it instead of animated dots."""
        self.hide_typing_indicator()
        # Pass initial_text to TypingIndicator so it can display the incoming log
        self.typing_indicator = TypingIndicator(parent=self.chat_container, initial_text=message)
        container = QWidget(); layout = QHBoxLayout(container); layout.setContentsMargins(0, 4, 0, 4)
        layout.addWidget(self.typing_indicator); layout.addStretch()
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container)
        QTimer.singleShot(10, self.scroll_to_bottom)

    def on_log_message(self, msg: str):
        """Slot called when unified_agent emits an INFO log. Show it in typing indicator."""
        try:
            # If typing indicator not present, show it with the message
            if not self.typing_indicator:
                self.show_typing_indicator(message=msg)
            else:
                # Update existing indicator text
                self.typing_indicator.update_text(msg)
            QTimer.singleShot(10, self.scroll_to_bottom)
            QApplication.processEvents()
        except Exception:
            pass

    def hide_typing_indicator(self):
        if self.typing_indicator:
            self.typing_indicator.stop_animation()
            widget = self.typing_indicator.parent()
            if widget:
                self.chat_layout.removeWidget(widget)
                widget.deleteLater()
            self.typing_indicator = None

    def scroll_to_bottom(self):
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def on_send(self):
        text = self.input_field.text().strip()
        if not text: return
        self.add_chat_bubble(text, is_user=True)
        self.input_field.clear(); self.input_field.setDisabled(True); self.send_btn.setDisabled(True)
        self.show_typing_indicator()
        # Pass the optional shared async runner if the agent exposes it
        runner = getattr(self.agent, '_runner', None)
        self.worker = Worker(text, self.agent, runner=runner); self.worker.finished.connect(self.on_response); self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_response(self, response: str):
        self.hide_typing_indicator()
        self.add_chat_bubble(response, is_user=False)
        self.input_field.setDisabled(False); self.send_btn.setDisabled(False); self.input_field.setFocus()

    def on_error(self, err: str):
        self.hide_typing_indicator()
        self.add_chat_bubble(f"Error: {err}", is_user=False)
        self.input_field.setDisabled(False); self.send_btn.setDisabled(False)

    def on_upload_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select File')
        if file_path:
            filename = os.path.basename(file_path)
            # Directly call the agent's tool for consistency
            self.add_chat_bubble(f"Uploading file: {filename}...", is_user=True)
            self.on_send() # Let the on_send flow handle the worker
            self.input_field.setText(f"Summarize the document '{filename}'")
            # The agent will handle the upload via its tool `upload_file_to_vault`
            # and the user will see the result in the chat.
            self.update_vault_info()
            self.input_field.setFocus()

# -----------------------------------------------------------------------------
# APP ENTRY (REFACTORED FOR UNIFIED AGENT)
# -----------------------------------------------------------------------------
def run_gui(agent, runner=None):
    """
    Launches the PyQt6 GUI for the Unified Agent.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    font = QFont('Segoe UI', 9)
    app.setFont(font)
    
    # Attach runner to agent for worker threads to reuse (non-invasive)
    if runner is not None:
        try:
            setattr(agent, '_runner', runner)
        except Exception:
            pass

    window = ChatWindow(agent)
    window.show()
    # Always start the Qt event loop so the window is actually shown.
    # The caller (unified_interface or this module's __main__) can
    # ignore or use the returned exit code as needed.
    return app.exec()


if __name__ == '__main__':
    # This block is for standalone testing of the GUI.
    # It requires a mock/dummy agent to be passed.
    class MockAgent:
        def run(self, query):
            return asyncio.run(self.async_run(query))
        async def async_run(self, query):
            await asyncio.sleep(1)
            return {'status': 'success', 'result': f"Mock response to: '{query}'"}

    run_gui(MockAgent())
