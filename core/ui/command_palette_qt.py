import threading
from typing import Any

import pythoncom
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)
from qfluentwidgets import LineEdit

from core.infra.logger_config import logger
from core.plugins.plugin_manager import plugin_manager


class QtCommandPaletteDialog(QDialog):
    """PySide6 Frameless Fluent Command Palette Dialog with Grouped Categories."""

    def __init__(self, palette_manager: Any, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.palette_manager = palette_manager
        self.show_more_history = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(640, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)

        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.search_bar = LineEdit(self)
        self.search_bar.setPlaceholderText(
            "Digite uma instrução para a IA ou busque um comando..."
        )
        self.search_bar.textChanged.connect(self._on_text_changed)
        search_layout.addWidget(self.search_bar, stretch=1)

        self.send_ai_btn = QPushButton("Enviar para IA 🚀", self)
        self.send_ai_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            """
        )
        self.send_ai_btn.clicked.connect(self._send_custom_ai)
        search_layout.addWidget(self.send_ai_btn)

        layout.addLayout(search_layout)

        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet(
            """
            QListWidget {
                background-color: #1f1f1f;
                color: #ffffff;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            """
        )
        self.list_widget.itemDoubleClicked.connect(self._execute_selected)
        layout.addWidget(self.list_widget)

        self.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True
            elif event.key() == Qt.Key.Key_Down:
                self._move_selection(1)
                return True
            elif event.key() == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._execute_selected()
                return True
        elif event.type() == QEvent.Type.WindowDeactivate:
            self.hide()
            return True
        return super().eventFilter(watched, event)

    def _move_selection(self, step: int) -> None:
        count = self.list_widget.count()
        if count == 0:
            return
        cur = self.list_widget.currentRow()
        new_row = cur + step
        while 0 <= new_row < count:
            item = self.list_widget.item(new_row)
            if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self.list_widget.setCurrentRow(new_row)
                break
            new_row += step

    def _on_text_changed(self, text: str) -> None:
        self.palette_manager._filter_commands(text)
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.list_widget.clear()

        # 1. Section: PLUGINS E INTENTS at top
        plugin_items = [
            c
            for c in self.palette_manager.filtered_commands
            if c["action_type"] == "plugin"
        ]
        if plugin_items:
            header = QListWidgetItem("── PLUGINS E INTENTS ──")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(header)
            for cmd in plugin_items:
                item = QListWidgetItem(cmd["label"])
                item.setData(Qt.ItemDataRole.UserRole, cmd)
                self.list_widget.addItem(item)

        # 2. Section: HISTÓRICO RECENTE at bottom
        history_all = [
            c
            for c in self.palette_manager.filtered_commands
            if c["action_type"] == "history"
        ]
        history_limit = 15 if self.show_more_history else 5
        history_items = history_all[:history_limit]

        if history_all:
            header = QListWidgetItem("── HISTÓRICO RECENTE ──")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(header)
            for cmd in history_items:
                item = QListWidgetItem(cmd["label"])
                item.setData(Qt.ItemDataRole.UserRole, cmd)
                self.list_widget.addItem(item)

            # Button item for "Mostrar Mais / Mostrar Menos"
            more_label = (
                "➖  Mostrar menos histórico"
                if self.show_more_history
                else "➕  Mostrar mais histórico..."
            )
            more_item = QListWidgetItem(more_label)
            more_cmd = {
                "action_type": "toggle_more_history",
                "label": more_label,
            }
            more_item.setData(Qt.ItemDataRole.UserRole, more_cmd)
            more_item.setForeground(Qt.GlobalColor.cyan)
            self.list_widget.addItem(more_item)

        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).flags() & Qt.ItemFlag.ItemIsSelectable:
                self.list_widget.setCurrentRow(i)
                break

    def _send_custom_ai(self) -> None:
        text = self.search_bar.text().strip()
        if text:
            self.hide()
            cmd = {
                "label": text,
                "action_type": "history",
                "command_text": text,
                "intent": "ai_cmd",
                "risk_level": "safe",
            }
            self.palette_manager._run_command_action(cmd)

    def _execute_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item and item.flags() & Qt.ItemFlag.ItemIsSelectable:
            cmd = item.data(Qt.ItemDataRole.UserRole)
            if not cmd:
                return

            if cmd.get("action_type") == "toggle_more_history":
                self.show_more_history = not self.show_more_history
                self._refresh_list()
                return

            self.hide()
            self.palette_manager._run_command_action(cmd)
        else:
            self._send_custom_ai()


class QtCommandPalette(QObject):
    """Manager for QtCommandPalette interacting with hotkeys and dispatcher."""

    trigger_show = Signal()

    def __init__(self, dispatcher: Any) -> None:
        super().__init__()
        self.dispatcher = dispatcher
        self.all_commands: list[dict[str, Any]] = []
        self.filtered_commands: list[dict[str, Any]] = []
        self.dialog: QtCommandPaletteDialog | None = None
        self.trigger_show.connect(self._on_trigger_show)

    def _fetch_commands(self) -> None:
        self.all_commands = []

        intents = plugin_manager.get_intents()
        for i in intents:
            self.all_commands.append(
                {
                    "label": f"🔌  {i['intent']} — {i['description']}",
                    "action_type": "plugin",
                    "intent": i["intent"],
                    "risk_level": i["risk_level"],
                }
            )

        try:
            from core.persistence.history_db import history_manager

            recent_cmds = history_manager.get_recent_commands(limit=15)
            for cmd_str in recent_cmds:
                self.all_commands.append(
                    {
                        "label": f"🕒  {cmd_str}",
                        "action_type": "history",
                        "command_text": cmd_str,
                        "intent": "system_cmd",
                        "risk_level": "safe",
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to fetch history for command palette: {e}")

        self.filtered_commands = self.all_commands.copy()

    def _filter_commands(self, query: str) -> None:
        q = query.lower().strip()
        if not q:
            self.filtered_commands = self.all_commands.copy()
        else:
            self.filtered_commands = [
                c
                for c in self.all_commands
                if q in c["label"].lower() or q in c.get("command_text", "").lower()
            ]

    def _run_command_action(self, selected_cmd: dict[str, Any]) -> None:
        def run_action() -> None:
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass
            try:
                if selected_cmd["action_type"] == "history":
                    cmd_text = selected_cmd["command_text"]
                    logger.info(
                        f"Command Palette dispatching history/text to AI: '{cmd_text}'"
                    )
                    self.dispatcher.dispatch(cmd_text)
                elif selected_cmd["action_type"] == "plugin":
                    action_config = {
                        "action": "plugin",
                        "intent": selected_cmd["intent"],
                        "risk_level": selected_cmd["risk_level"],
                    }
                    self.dispatcher.last_input_text = selected_cmd["label"]
                    self.dispatcher.last_input_source = "command_palette"
                    self.dispatcher.last_confidence = 1.0
                    self.dispatcher.handle_dynamic(action_config)
            except Exception as e:
                logger.error(f"Error executing command palette action: {e}")
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        threading.Thread(target=run_action, daemon=True).start()

    def show(self) -> None:
        self.trigger_show.emit()

    def _on_trigger_show(self) -> None:
        self._fetch_commands()
        if not self.dialog:
            self.dialog = QtCommandPaletteDialog(self)
        self.dialog._refresh_list()
        self.dialog.show()
        self.dialog.activateWindow()
        self.dialog.search_bar.setFocus()
