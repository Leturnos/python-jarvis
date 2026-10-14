import threading
from typing import Any

import pythoncom
from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)
from qfluentwidgets import LineEdit

from core.infra.logger_config import logger
from core.persistence.history_db import history_manager
from core.plugins.plugin_manager import plugin_manager
from core.runtime.state import JarvisState, state_manager

CATEGORY_ORDER = [
    "Sistema",
    "Desenvolvimento",
    "Internet",
    "Mídia",
    "Produtividade",
    "Jogos",
    "Geral",
]

CATEGORY_HEADERS = {
    "Sistema": "── 🖥️ SISTEMA WINDOWS ──",
    "Desenvolvimento": "── 💻 DESENVOLVIMENTO & TERMINAIS ──",
    "Internet": "── 🌐 NAVEGAÇÃO & WEB ──",
    "Mídia": "── 🎵 MÍDIA & ÁUDIO ──",
    "Produtividade": "── 📋 PRODUTIVIDADE & NOTAS ──",
    "Jogos": "── 🎮 JOGOS & LAUNCHERS ──",
    "Geral": "── ⚡ OUTROS COMANDOS ──",
}

CATEGORY_ICONS = {
    "Sistema": "🖥️",
    "Desenvolvimento": "💻",
    "Internet": "🌐",
    "Mídia": "🎵",
    "Produtividade": "📋",
    "Jogos": "🎮",
    "Geral": "⚡",
}

CATEGORY_TAGS = {
    "@dev": "Desenvolvimento",
    "@codigo": "Desenvolvimento",
    "@code": "Desenvolvimento",
    "@sys": "Sistema",
    "@sistema": "Sistema",
    "@win": "Sistema",
    "@web": "Internet",
    "@net": "Internet",
    "@midia": "Mídia",
    "@media": "Mídia",
    "@som": "Mídia",
    "@prod": "Produtividade",
    "@game": "Jogos",
    "@jogos": "Jogos",
    "@games": "Jogos",
    "@hist": "Histórico",
    "@historico": "Histórico",
}


class QtCommandPaletteDialog(QDialog):
    """PySide6 Frameless Fluent Command Palette Dialog with Categorized Grouping."""

    def __init__(self, palette_manager: Any, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.palette_manager = palette_manager
        self.show_more_history = False
        self._is_active = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)

        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.search_bar = LineEdit(self)
        self.search_bar.setPlaceholderText(
            "Buscar comando ou usar @dev, @sys, @web, @midia, @prod..."
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
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
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
        elif event.type() == QEvent.Type.WindowActivate:
            self._is_active = True
            return False
        elif event.type() == QEvent.Type.WindowDeactivate:
            if self._is_active:
                self.hide()
                self._is_active = False
                return True
            return False
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

    def _append_header(self, text: str) -> None:
        header = QListWidgetItem(text)
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        header.setForeground(Qt.GlobalColor.gray)
        self.list_widget.addItem(header)

    def _append_history_section(
        self, history_all: list[dict[str, Any]], limit: int | None = None
    ) -> None:
        if not history_all:
            return
        history_items = history_all[:limit] if limit else history_all
        self._append_header("── 🕒 HISTÓRICO RECENTE ──")
        for cmd in history_items:
            item = QListWidgetItem(cmd["label"])
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            self.list_widget.addItem(item)

        if limit and len(history_all) > 5:
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

    def _append_plugins_by_category(self, plugin_items: list[dict[str, Any]]) -> None:
        for cat in CATEGORY_ORDER:
            cat_cmds = [c for c in plugin_items if c.get("category") == cat]
            if cat_cmds:
                header_text = CATEGORY_HEADERS.get(cat, f"── 🔌 {cat.upper()} ──")
                self._append_header(header_text)
                for cmd in cat_cmds:
                    item = QListWidgetItem(cmd["label"])
                    item.setData(Qt.ItemDataRole.UserRole, cmd)
                    self.list_widget.addItem(item)

        # Catch-all for any other categories
        other_cmds = [
            c for c in plugin_items if c.get("category") not in CATEGORY_ORDER
        ]
        if other_cmds:
            self._append_header("── 🔌 OUTROS COMANDOS ──")
            for cmd in other_cmds:
                item = QListWidgetItem(cmd["label"])
                item.setData(Qt.ItemDataRole.UserRole, cmd)
                self.list_widget.addItem(item)

    def _refresh_list(self) -> None:
        self.list_widget.clear()

        is_search_empty = not getattr(self.palette_manager, "current_query", "")

        history_items = [
            c
            for c in self.palette_manager.filtered_commands
            if c["action_type"] == "history"
        ]
        plugin_items = [
            c
            for c in self.palette_manager.filtered_commands
            if c["action_type"] == "plugin"
        ]

        # Case 1: Empty Search (Opening State) -> History at Top, followed by Categorized Plugins
        if is_search_empty:
            history_limit = 15 if self.show_more_history else 5
            self._append_history_section(history_items, limit=history_limit)
            self._append_plugins_by_category(plugin_items)

        # Case 2: Searching / Filtering State -> Show matched history if any, then matched categorized plugins
        else:
            self._append_history_section(history_items, limit=None)
            self._append_plugins_by_category(plugin_items)

        # Auto-select first selectable item
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
    """Manager for QtCommandPalette interacting with hotkeys, fuzzy search, and dispatcher."""

    trigger_show = Signal()

    def __init__(self, dispatcher: Any) -> None:
        super().__init__()
        self.dispatcher = dispatcher
        self.all_commands: list[dict[str, Any]] = []
        self.filtered_commands: list[dict[str, Any]] = []
        self.current_query: str = ""
        self.dialog: QtCommandPaletteDialog | None = None
        self.trigger_show.connect(self._on_trigger_show)

    def _fetch_commands(self) -> None:
        self.all_commands = []

        intents = plugin_manager.get_intents()
        for i in intents:
            category = i.get("category", "Geral")
            cat_icon = CATEGORY_ICONS.get(category, "⚡")
            friendly_name = i["intent"].replace("_", " ").title()
            self.all_commands.append(
                {
                    "label": f"{cat_icon}  {friendly_name}  [{category}] — {i['description']}",
                    "raw_name": friendly_name,
                    "action_type": "plugin",
                    "intent": i["intent"],
                    "description": i.get("description", ""),
                    "category": category,
                    "plugin_name": i.get("plugin_name", ""),
                    "phrases": i.get("phrases", []),
                    "risk_level": i.get("risk_level", "safe"),
                }
            )

        try:
            recent_cmds = history_manager.get_recent_commands(limit=15)
            for cmd_str in recent_cmds:
                self.all_commands.append(
                    {
                        "label": f"🕒  {cmd_str}",
                        "action_type": "history",
                        "command_text": cmd_str,
                        "intent": "system_cmd",
                        "category": "Histórico",
                        "risk_level": "safe",
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to fetch history for command palette: {e}")

        self.current_query = ""
        self.filtered_commands = self.all_commands.copy()

    def _filter_commands(self, query: str) -> None:
        q = query.lower().strip()
        self.current_query = q
        if not q:
            self.filtered_commands = self.all_commands.copy()
            return

        target_category = None
        search_term = q

        for tag, cat_name in CATEGORY_TAGS.items():
            if q == tag or q.startswith(tag + " ") or q.startswith(tag + ":"):
                target_category = cat_name
                search_term = q[len(tag) :].lstrip(" :").strip()
                break

        matched = []
        for c in self.all_commands:
            if target_category and c.get("category") != target_category:
                continue

            if search_term:
                searchable_text = " ".join(
                    [
                        c.get("label", ""),
                        c.get("intent", ""),
                        c.get("raw_name", ""),
                        c.get("description", ""),
                        c.get("category", ""),
                        c.get("command_text", ""),
                        " ".join(c.get("phrases", [])),
                    ]
                ).lower()
                if search_term in searchable_text:
                    matched.append(c)
            else:
                matched.append(c)

        self.filtered_commands = matched

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
                    intent_name = selected_cmd["intent"]
                    risk_level = selected_cmd.get("risk_level", "safe")
                    logger.info(
                        f"Command Palette dispatching plugin intent: '{intent_name}' (risk: {risk_level})"
                    )
                    action_payload = {
                        "action": "plugin",
                        "intent": intent_name,
                        "risk_level": risk_level,
                    }
                    self.dispatcher.handle_dynamic(action_payload)
            except Exception as e:
                logger.error(
                    f"Command Palette background execution failed: {e}",
                    exc_info=True,
                )
            finally:
                if state_manager.get_state() != JarvisState.IDLE:
                    logger.warning(
                        f"State was {state_manager.get_state()} after Command Palette execution. Resetting to IDLE."
                    )
                    state_manager.set_state(JarvisState.IDLE)

        threading.Thread(target=run_action, daemon=True).start()

    def show(self) -> None:
        self.trigger_show.emit()

    def _on_trigger_show(self) -> None:
        if not self.dialog:
            self.dialog = QtCommandPaletteDialog(self)

        self._fetch_commands()
        self.dialog.search_bar.clear()
        self.dialog._refresh_list()

        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        if not screen:
            screen = QApplication.primaryScreen()

        if screen:
            screen_geo = screen.geometry()
            x = screen_geo.x() + (screen_geo.width() - self.dialog.width()) // 2
            y = screen_geo.y() + (screen_geo.height() - self.dialog.height()) // 3
            self.dialog.move(x, y)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        self.dialog.search_bar.setFocus()
