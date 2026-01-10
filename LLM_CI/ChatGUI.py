from __future__ import annotations

import os
import sys
from datetime import datetime

import markdown
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
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
    from Utils import format_results_as_markdown, get_llm_provider, process_prompt, reset_chat_usage_log, system_message
except ImportError:
    def get_llm_provider():
        return None

    def process_prompt(prompt, llm, verbose, usage_mode):
        return f"Echo: {prompt}"

    def reset_chat_usage_log():
        pass

    system_message = 'You are a helpful DevOps assistant.'

try:
    from database_tools import execute_query, is_safe_select_query, validate_and_fix_sql
except Exception:
    validate_and_fix_sql = None
    is_safe_select_query = None
    execute_query = None
try:
    from pdf_generator import generate_pdf_from_results
except Exception:
    generate_pdf_from_results = None

import re

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem, QTextEdit

try:
    from Tools import get_vault_count
except Exception:
    def get_vault_count(vp=None):
        return 0

try:
    from Utils import _load_vault_embedding_cache
except Exception:
    def _load_vault_embedding_cache(vp=None):
        return None, []

# -----------------------------------------------------------------------------
# WORKER THREAD
# -----------------------------------------------------------------------------


class Worker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    thinking_started = pyqtSignal()
    thinking_stopped = pyqtSignal()

    def __init__(self, prompt: str, llm, conversation_history: list = None, parent=None):
        super().__init__(parent)
        self.prompt = prompt
        self.llm = llm
        self.conversation_history = conversation_history or []
        self.updated_history = None
        self.generated_sql = None

    def run(self):
        try:
            self.thinking_started.emit()
            # Database queries are now handled through tools - let the LLM use the database tools directly
            # Always pass conversation_history (may be empty list or contain prior messages)
            result = process_prompt(
                self.prompt,
                self.llm,
                verbose=False,
                usage_mode='chat',
                conversation_history=self.conversation_history
            )

            # Handle both return formats: (response, history) or just response
            if isinstance(result, tuple):
                response, updated_history = result
                # Store the updated history in a way the GUI can access it
                self.updated_history = updated_history
            else:
                response = result
                self.updated_history = None

            self.thinking_stopped.emit()
            # Emit the response text; GUI will pick up generated_sql via worker.generated_sql
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
        self.label = QLabel('...')
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
        self.label.setText('•' * self.dot_count)

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

        # Convert Markdown to HTML
        html_message = markdown.markdown(
            message, extensions=['fenced_code', 'codehilite', 'tables', 'nl2br']
        )

        # 2. Use QLabel for rich text display so it wraps and doesn't show internal scrollbars
        from PyQt6.QtWidgets import QLabel
        self.text_browser = QLabel()
        self.text_browser.setTextFormat(Qt.TextFormat.RichText)
        self.text_browser.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setWordWrap(True)
        self.text_browser.setText(html_message)

        font = QFont('Segoe UI')
        font.setPixelSize(13)
        self.text_browser.setFont(font)
        self.text_browser.setStyleSheet('border: none; background: transparent; padding: 8px;')

        # Add content
        self.layout.addWidget(self.text_browser)
        # Assign names for more specific styling below
        self.text_browser.setObjectName('message_label')

        # Timestamp (small, subtle)
        self.time_label = QLabel(timestamp)
        self.time_label.setFont(QFont('Segoe UI', 8))
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        if date_tooltip:
            self.time_label.setToolTip(date_tooltip)
        self.layout.addWidget(self.time_label)

        # 4. Styling: flat rectangular message spanning most of the width
        if is_user:
            bg = '#e6fff2'
            text_color = '#002b20'
        else:
            bg = '#f7f9fb'
            # Make assistant text darker for better readability
            text_color = '#07121a'

        # Apply styles to the message frame
        self.setStyleSheet(f"""
            MessageBubble {{
                background-color: {bg};
                border-radius: 8px;
                margin: 6px 0px;
            }}
            QLabel#message_label {{
                color: {text_color};
                background: transparent;
            }}
            QLabel#timestamp_label {{
                color: #777777;
                background: transparent;
            }}
        """)

        # Ensure timestamp label has an object name for styling
        self.time_label.setObjectName('timestamp_label')

# -----------------------------------------------------------------------------
# UI COMPONENT: Message Row
# -----------------------------------------------------------------------------


class MessageRow(QWidget):
    def __init__(self, message: str, is_user: bool, timestamp: str, date_tooltip: str = None, parent=None):
        super().__init__(parent)
        # Use a single-column layout; messages span the width with padding
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(6, 4, 6, 4)
        self.layout.setSpacing(2)

        self.bubble = MessageBubble(message, is_user, timestamp, date_tooltip)
        self.bubble.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.layout.addWidget(self.bubble)

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
        # Initialize conversation history with the system message so context is preserved
        self.conversation_history = [('system', system_message)]  # Maintain conversation history
        self.pending_sql = None
        self.last_results = None
        self.typing_indicator = None
        self.typing_row = None
        self.setWindowTitle('MCP — DevOps Chat')
        self.resize(800, 950)

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
        h_layout.addStretch()
        # Vault info: document count and cache status
        self.doc_count_label = QLabel('Docs: 0')
        self.doc_count_label.setStyleSheet('color: white; font-size: 12px;')
        self.cache_label = QLabel('Cache: none')
        self.cache_label.setStyleSheet('color: white; font-size: 12px;')
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 6, 12, 6)
        info_layout.addWidget(self.doc_count_label)
        info_layout.addWidget(self.cache_label)
        info_widget = QWidget()
        info_widget.setLayout(info_layout)
        h_layout.addWidget(info_widget)
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

        # Action buttons (Execute / Cancel / Export PDF) - hidden unless a pending SQL exists
        action_frame = QFrame()
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(10, 6, 10, 6)
        action_layout.setSpacing(8)

        self.exec_btn = QPushButton('Execute')
        self.exec_btn.setEnabled(False)
        self.exec_btn.clicked.connect(self.on_execute_clicked)
        self.cancel_btn = QPushButton('Cancel')
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.on_cancel_clicked)
        self.export_pdf_btn = QPushButton('Export PDF')
        self.export_pdf_btn.setEnabled(False)
        self.export_pdf_btn.clicked.connect(self.on_export_pdf_clicked)

        action_layout.addStretch()
        action_layout.addWidget(self.exec_btn)
        action_layout.addWidget(self.cancel_btn)
        action_layout.addWidget(self.export_pdf_btn)
        main_vbox.addWidget(action_frame)

        # 4. Initialize System
        reset_chat_usage_log()
        self.add_chat_bubble(system_message, is_user=False)
        # Update vault-related UI info (counts / cache)
        try:
            self.update_vault_info()
        except Exception:
            pass

    def update_vault_info(self):
        """Update the document count and embedding cache status labels."""
        try:
            count = get_vault_count()
        except Exception:
            count = 0
        try:
            emb, lines = _load_vault_embedding_cache()
        except Exception:
            emb, lines = None, []

        self.doc_count_label.setText(f"Docs: {count}")
        if emb is not None:
            try:
                dim = int(emb.shape[1]) if hasattr(emb, 'shape') and len(emb.shape) > 1 else (emb.shape[0] if hasattr(emb, 'shape') else 0)
            except Exception:
                dim = 0
            self.cache_label.setText(f"Cache: {len(lines)} × {dim}d")
        else:
            self.cache_label.setText('Cache: none')
    # -------------------------------------------------------------------------
    # UNIFIED MESSAGE SYSTEM
    # -------------------------------------------------------------------------

    def add_chat_bubble(self, text: str, is_user: bool):
        """Adds a single chat bubble to the display."""
        self.add_chat_bubbles([(text, is_user)])

    def add_chat_bubbles(self, messages: list[tuple[str, bool]]):
        """Adds a list of chat bubbles to the display."""
        for text, is_user in messages:
            now = datetime.now()
            ts = now.strftime('%H:%M')
            dt_tooltip = now.strftime('%A, %B %d, %Y')

            row = MessageRow(text, is_user, ts, dt_tooltip, parent=self.chat_container)
            # Insert at the second to last position to keep the stretch at the bottom
            self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)

        # Use a single timer to scroll to the bottom after all messages are added
        QTimer.singleShot(10, self.scroll_to_bottom)
        QApplication.processEvents()

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

        # Handle approval commands for pending SQL before sending to the LLM
        exec_cmds = ['/execute', 'execute', '/excute', 'excute', '/run', 'run']
        cancel_cmds = ['/cancel', 'cancel']

        if text.strip().lower() in exec_cmds and self.pending_sql:
            # Execute the pending SQL safely (normalize and strip trailing semicolons)
            if not validate_and_fix_sql or not execute_query:
                self.add_chat_bubble('Database functionality is not available.', is_user=False)
                self.pending_sql = None
            else:
                sql_to_exec = self.pending_sql.rstrip().rstrip(';')
                ok, safety_msg = is_safe_select_query(sql_to_exec) if is_safe_select_query else (False, 'DB tools unavailable')
                if not ok:
                    self.add_chat_bubble(f'Query blocked: {safety_msg}', is_user=False)
                    self.pending_sql = None
                else:
                    is_valid, msg, fixed_sql = validate_and_fix_sql(sql_to_exec)
                    if not is_valid:
                        self.add_chat_bubble(f'Cannot execute query: {msg}', is_user=False)
                        self.pending_sql = None
                    else:
                        rows, err = execute_query(fixed_sql)
                        if err:
                            self.add_chat_bubble(f'Execution error: {err}', is_user=False)
                        else:
                            # Format results as a Markdown table for consistent rendering
                            table_md = format_results_as_markdown(rows, max_rows=5)
                            self.add_chat_bubble(f'Query executed successfully. Results (first {min(5, len(rows))} rows):\n\n{table_md}', is_user=False)
                        self.pending_sql = None
            self.input_field.clear()
            return

        if text.strip().lower() in cancel_cmds and self.pending_sql:
            self.add_chat_bubble('Cancelled pending query.', is_user=False)
            self.pending_sql = None
            self.input_field.clear()
            return

        # Normal flow: send user message to worker
        self.add_chat_bubble(text, is_user=True)
        self.input_field.clear()
        self.input_field.setDisabled(True)
        self.send_btn.setDisabled(True)

        self.show_typing_indicator()

        self.worker = Worker(text, self.llm, conversation_history=self.conversation_history)
        self.worker.thinking_started.connect(self.on_thinking_started)
        self.worker.thinking_stopped.connect(self.on_thinking_stopped)
        self.worker.finished.connect(self.on_response)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def _update_action_buttons(self):
        enabled = bool(self.pending_sql)
        self.exec_btn.setEnabled(enabled)
        self.cancel_btn.setEnabled(enabled)
        # Export PDF is enabled only if we have last_results
        self.export_pdf_btn.setEnabled(bool(self.last_results))

    def _extract_sql_from_text(self, text: str) -> str | None:
        """Try to find a SQL SELECT statement within arbitrary text.

        Returns the SQL string (without trailing semicolon) or None.
        """
        if not text:
            return None

        # Look for fenced code blocks with sql
        fenced = re.search(r'```(?:sql)?\s*([\s\S]*?)```', text, flags=re.IGNORECASE)
        if fenced:
            candidate = fenced.group(1).strip()
            m = re.search(r'SELECT\b[\s\S]*', candidate, flags=re.IGNORECASE)
            if m:
                return m.group(0).strip().rstrip(';')

        # Otherwise, search for the first SELECT ... ; or end of text
        m = re.search(r'(SELECT\b[\s\S]*?)(;|$)', text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(';')

        return None

    def _show_sql_preview_modal(self, sql: str):
        """Display a modal dialog showing the SQL and a few sample rows; user can Approve or Cancel."""
        dialog = QDialog(self)
        dialog.setWindowTitle('SQL Preview')
        vbox = QVBoxLayout(dialog)

        sql_box = QTextEdit()
        sql_box.setReadOnly(True)
        sql_box.setPlainText(sql)
        vbox.addWidget(sql_box)

        # Attempt to show a few sample rows (safe: LIMIT 5)
        sample_rows = []
        if validate_and_fix_sql and execute_query:
            try:
                ok, msg, fixed = validate_and_fix_sql(sql)
                if ok:
                    preview_sql = fixed.rstrip().rstrip(';') + ' LIMIT 5'
                    rows, err = execute_query(preview_sql)
                    if not err and rows:
                        sample_rows = rows
            except Exception:
                sample_rows = []

        if sample_rows:
            table = QTableWidget()
            cols = list(sample_rows[0].keys())
            table.setColumnCount(len(cols))
            table.setHorizontalHeaderLabels(cols)
            table.setRowCount(len(sample_rows))
            for r, row in enumerate(sample_rows):
                for c, col in enumerate(cols):
                    item = QTableWidgetItem(str(row.get(col, '')))
                    table.setItem(r, c, item)
            vbox.addWidget(table)
        # Use Ok/Cancel buttons, but label Ok as 'Approve query' and make it execute
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        vbox.addWidget(buttons)

        # Change Ok button text to 'Approve query'
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText('Approve query')

        def on_accept():
            # Reflect the user's approval as a user message
            self.add_chat_bubble('Approve query', is_user=True)
            try:
                dialog.accept()
                sql_to_exec = sql.rstrip().rstrip(';')
                # Basic availability checks
                if not validate_and_fix_sql or not execute_query:
                    self.add_chat_bubble('Database functionality is not available.', is_user=False)
                    return

                ok, safety_msg = is_safe_select_query(sql_to_exec) if is_safe_select_query else (False, 'DB tools unavailable')
                if not ok:
                    self.add_chat_bubble(f'Query blocked: {safety_msg}', is_user=False)
                    return

                is_valid, msg, fixed_sql = validate_and_fix_sql(sql_to_exec)
                if not is_valid:
                    self.add_chat_bubble(f'Cannot execute query: {msg}', is_user=False)
                    return

                rows, err = execute_query(fixed_sql)
                if err:
                    self.add_chat_bubble(f'Execution error: {err}', is_user=False)
                    return

                # Store results for export
                self.last_results = rows
                # Format as markdown table
                try:
                    from Utils import format_results_as_markdown
                    table_md = format_results_as_markdown(rows, max_rows=10)
                except Exception:
                    import json
                    table_md = json.dumps(rows[:10], indent=2, default=str)

                self.add_chat_bubble(f'Query executed. Results (first {min(10, len(rows))} rows):\n\n{table_md}', is_user=False)
                self.pending_sql = None
                self._update_action_buttons()
            except Exception as e:
                self.add_chat_bubble(f'Error executing SQL from preview: {e}', is_user=False)

        def on_reject():
            # Show user action as a sent message
            self.add_chat_bubble('Cancel', is_user=True)
            dialog.reject()
            self.pending_sql = None
            self._update_action_buttons()

        buttons.accepted.connect(on_accept)
        buttons.rejected.connect(on_reject)

        dialog.setLayout(vbox)
        dialog.exec()

    def on_execute_clicked(self):
        # Trigger same logic as typed /execute
        # Reflect user clicking the Execute button
        self.add_chat_bubble('Execute', is_user=True)

        if not self.pending_sql:
            self.add_chat_bubble('No pending SQL to execute.', is_user=False)
            return

        sql_to_exec = self.pending_sql.rstrip().rstrip(';')
        if not validate_and_fix_sql or not execute_query:
            self.add_chat_bubble('Database functionality not available.', is_user=False)
            self.pending_sql = None
            self._update_action_buttons()
            return

        ok, safety_msg = is_safe_select_query(sql_to_exec)
        if not ok:
            self.add_chat_bubble(f'Query blocked: {safety_msg}', is_user=False)
            self.pending_sql = None
            self._update_action_buttons()
            return

        is_valid, msg, fixed_sql = validate_and_fix_sql(sql_to_exec)
        if not is_valid:
            self.add_chat_bubble(f'Cannot execute query: {msg}', is_user=False)
            self.pending_sql = None
            self._update_action_buttons()
            return

        rows, err = execute_query(fixed_sql)
        if err:
            self.add_chat_bubble(f'Execution error: {err}', is_user=False)
            self.pending_sql = None
            self._update_action_buttons()
            return

        # Store last results for PDF export
        self.last_results = rows
        # Format results: Markdown table for multiple rows, key: value lines for single row
        try:
            if rows and len(rows) > 1:
                table_md = format_results_as_markdown(rows, max_rows=10)
                self.add_chat_bubble(f'Query executed. Results (first {min(10, len(rows))} rows):\n\n{table_md}', is_user=False)
            elif rows and len(rows) == 1:
                single = rows[0]
                if isinstance(single, dict):
                    lines = '\n'.join(f"{k}: {v}" for k, v in single.items())
                    self.add_chat_bubble(f'Query executed. Result:\n\n{lines}', is_user=False)
                else:
                    self.add_chat_bubble(f'Query executed. Result:\n\n{str(single)}', is_user=False)
            else:
                self.add_chat_bubble('Query executed. No rows returned.', is_user=False)
        except Exception:
            import json
            snippet = json.dumps(rows[:10], indent=2, default=str)
            more = f"\n... ({len(rows)} rows)" if len(rows) > 10 else ''
            self.add_chat_bubble(f'Query executed. Results (first {min(10, len(rows))} rows):\n{snippet}{more}', is_user=False)
        self.pending_sql = None
        self._update_action_buttons()

    def on_cancel_clicked(self):
        # Reflect user clicking the Cancel button
        self.add_chat_bubble('Cancel', is_user=True)
        if self.pending_sql:
            self.pending_sql = None
            self.add_chat_bubble('Pending SQL cancelled.', is_user=False)
        else:
            self.add_chat_bubble('Nothing to cancel.', is_user=False)
        self._update_action_buttons()

    def on_export_pdf_clicked(self):
        # Reflect user clicking the Export PDF button
        self.add_chat_bubble('Export PDF', is_user=True)
        if not self.last_results:
            self.add_chat_bubble('No results available to export.', is_user=False)
            return

        if not generate_pdf_from_results:
            self.add_chat_bubble('PDF generation functionality is not available. Install reportlab.', is_user=False)
            return

        try:
            pdf_path = generate_pdf_from_results(self.last_results, query='Exported results', title='Query Results')
            self.add_chat_bubble(f'The results have been exported to a PDF file: {pdf_path}', is_user=False)
        except Exception as e:
            self.add_chat_bubble(f'Error exporting PDF: {e}', is_user=False)

    def on_thinking_started(self):
        """Called when the agent starts processing"""
        pass  # Typing indicator is already shown

    def on_thinking_stopped(self):
        """Called when the agent finishes processing"""
        pass  # Will be hidden in on_response or on_error

    def on_response(self, response: str):
        self.hide_typing_indicator()
        # Convert repeated Key: value assistant responses into a table when possible
        try:
            from Utils import convert_kv_text_to_html, convert_kv_text_to_markdown
            converted_html = convert_kv_text_to_html(response)
            if converted_html:
                # Use the HTML table directly for better GUI layout
                self.add_chat_bubble(converted_html, is_user=False)
            else:
                # Fallback: try markdown conversion for CLI-like rendering
                converted_md = convert_kv_text_to_markdown(response)
                if converted_md:
                    self.add_chat_bubble(converted_md, is_user=False)
                else:
                    self.add_chat_bubble(response, is_user=False)
        except Exception:
            self.add_chat_bubble(response, is_user=False)
        # If the worker produced an updated conversation history, persist it
        if hasattr(self, 'worker') and getattr(self.worker, 'updated_history', None):
            self.conversation_history = self.worker.updated_history
        # If the worker generated SQL for approval, store it on the window
        # If worker generated SQL directly, use it
        if hasattr(self, 'worker') and getattr(self.worker, 'generated_sql', None):
            self.pending_sql = self.worker.generated_sql
            self.add_chat_bubble('A SQL query was generated and is ready for execution. You can Execute, Cancel, or Export PDF.', is_user=False)
            self._update_action_buttons()
        else:
            # Try to extract a SQL snippet anywhere in the assistant's response
            try:
                txt = response if isinstance(response, str) else ''
                sql = self._extract_sql_from_text(txt)
                if sql:
                    # Normalize and store
                    self.pending_sql = sql.strip().rstrip(';')
                    # Offer preview modal with sample rows
                    self._show_sql_preview_modal(self.pending_sql)
                    self._update_action_buttons()
            except Exception:
                pass
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
            # Append file to RAG vault and show status
            try:
                from Tools import upload_file_to_vault
                res = upload_file_to_vault(file_path)
            except Exception:
                res = f"Uploaded: {filename} (local only)"

            self.add_chat_bubble(f"📎 {res}", is_user=True)
            # Refresh vault UI info after upload
            try:
                self.update_vault_info()
            except Exception:
                pass
            # Pre-fill the input to let user ask the assistant about the file
            self.input_field.setText(f"Analyze the file {filename}...")
            self.input_field.setFocus()

# -----------------------------------------------------------------------------
# APP ENTRY
# -----------------------------------------------------------------------------


def run_gui():
    app = QApplication(sys.argv)
    font = QFont('Segoe UI', 9)
    app.setFont(font)
    # Preload RAG documents from configured folder (if any)
    try:
        from Tools import load_folder_to_vault
        rag_dir = os.getenv('RAG_DOCS_DIR') or os.getenv('VAULT_DIR')
        if rag_dir:
            try:
                load_folder_to_vault(rag_dir, vault_path='vault.txt')
                # Compute and cache embeddings so vector retrieval is available by default
                try:
                    from Utils import compute_and_cache_vault_embeddings
                    compute_and_cache_vault_embeddings(vault_path='vault.txt')
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass

    llm = get_llm_provider()
    window = ChatWindow(llm)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    run_gui()
