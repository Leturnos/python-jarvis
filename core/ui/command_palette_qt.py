import threading
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QVBoxLayout
from qfluentwidgets import LineEdit

from core.infra.logger_config import logger
from core.plugins.plugin_manager import plugin_manager


class QtCommandPaletteDialog(QDialog):
    """PySide6 Frameless Fluent Command Palette Dialog."""

    def __init__(self, palette_manager: Any, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.palette_manager = palette_manager
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(600, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.search_bar = LineEdit(self)
        self.search_bar.setPlaceholderText("Search commands or type an intent...")
        self.search_bar.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_bar)

        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet(
            """
            QListWidget {
                background-color: #202020;
                color: #ffffff;
                border: 1px solid #333333;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
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
                cur = self.list_widget.currentRow()
                if cur < self.list_widget.count() - 1:
                    self.list_widget.setCurrentRow(cur + 1)
                return True
            elif event.key() == Qt.Key.Key_Up:
                cur = self.list_widget.currentRow()
                if cur > 0:
                    self.list_widget.setCurrentRow(cur - 1)
                return True
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._execute_selected()
                return True
        elif event.type() == QEvent.Type.WindowDeactivate:
            self.hide()
            return True
        return super().eventFilter(watched, event)

    def _on_text_changed(self, text: str) -> None:
        self.palette_manager._filter_commands(text)
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for cmd in self.palette_manager.filtered_commands:
            item = QListWidgetItem(cmd["label"])
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _execute_selected(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.palette_manager.filtered_commands):
            cmd = self.palette_manager.filtered_commands[row]
            self.hide()
            self.palette_manager._run_command_action(cmd)


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
        try:
            from core.persistence.history_db import history_manager

            recent_cmds = history_manager.get_recent_commands(limit=10)
            for cmd_str in recent_cmds:
                self.all_commands.append(
                    {
                        "label": f"[Histórico] {cmd_str}",
                        "action_type": "history",
                        "command_text": cmd_str,
                        "intent": "system_cmd",
                        "risk_level": "safe",
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to fetch history for command palette: {e}")

        intents = plugin_manager.get_intents()
        for i in intents:
            self.all_commands.append(
                {
                    "label": f"[Plugin] {i['intent']} - {i['description']}",
                    "action_type": "plugin",
                    "intent": i["intent"],
                    "risk_level": i["risk_level"],
                }
            )

        self.filtered_commands = self.all_commands.copy()

    def _filter_commands(self, query: str) -> None:
        q = query.lower().strip()
        if not q:
            self.filtered_commands = self.all_commands.copy()
        else:
            self.filtered_commands = [
                c for c in self.all_commands if q in c["label"].lower()
            ]

    def _run_command_action(self, selected_cmd: dict[str, Any]) -> None:
        def run_action() -> None:
            if selected_cmd["action_type"] == "history":
                self.dispatcher.last_input_text = selected_cmd["command_text"]
                self.dispatcher.last_input_source = "command_palette"
                self.dispatcher.last_confidence = 1.0
                self.dispatcher.dispatch(selected_cmd["command_text"])
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
