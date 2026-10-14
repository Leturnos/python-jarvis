from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    InfoBar,
    PushButton,
    SimpleCardWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    SwitchButton,
    TransparentToolButton,
)

from core.infra.logger_config import logger
from core.plugins.plugin_manager import plugin_manager


class PluginCard(SimpleCardWidget):
    """Card representing an individual plugin preset with enable switch and expandable command list."""

    def __init__(
        self, plugin_info: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.plugin_info = plugin_info
        self.plugin_id = plugin_info["id"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Header: Name, Category Tag and Switch
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.title_label = StrongBodyLabel(
            plugin_info.get("name", self.plugin_id), self
        )
        header_layout.addWidget(self.title_label)

        category = plugin_info.get("category", "Geral")
        self.category_badge = CaptionLabel(f"[{category}]", self)
        self.category_badge.setStyleSheet("color: #0078d4; font-weight: bold;")
        header_layout.addWidget(self.category_badge)

        header_layout.addStretch(1)

        self.switch = SwitchButton(self)
        self.switch.setOnText("Ativo")
        self.switch.setOffText("Inativo")
        self.switch.setChecked(plugin_info.get("is_enabled", True))
        self.switch.checkedChanged.connect(self._on_switch_changed)
        header_layout.addWidget(self.switch)

        layout.addLayout(header_layout)

        # Description
        desc_text = plugin_info.get("description", "Sem descrição disponível.")
        self.desc_label = BodyLabel(desc_text, self)
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        # Footer Row: Count of commands & View Commands toggle button
        footer_layout = QHBoxLayout()
        count = plugin_info.get("commands_count", 0)
        plural = "s" if count != 1 else ""
        self.count_label = CaptionLabel(
            f"⚡ {count} comando{plural} disponível{plural}", self
        )
        footer_layout.addWidget(self.count_label)

        footer_layout.addStretch(1)

        self.toggle_details_btn = PushButton("Ver Comandos", self)
        self.toggle_details_btn.setFixedHeight(28)
        self.toggle_details_btn.clicked.connect(self._toggle_details)
        footer_layout.addWidget(self.toggle_details_btn)

        layout.addLayout(footer_layout)

        # Collapsible commands list container
        self.details_container = QFrame(self)
        self.details_container.setVisible(False)
        self.details_container.setStyleSheet(
            "background-color: rgba(128, 128, 128, 0.08); border-radius: 6px; padding: 6px;"
        )
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(10, 8, 10, 8)
        details_layout.setSpacing(8)

        commands = plugin_info.get("commands", [])
        if commands:
            for cmd in commands:
                intent_name = cmd.get("intent", "")
                desc = cmd.get("description", "")
                phrases = cmd.get("phrases", [])

                cmd_box = QVBoxLayout()
                cmd_box.setSpacing(2)
                cmd_box.setContentsMargins(0, 4, 0, 4)

                # 1. Main Command Item
                friendly_cmd = intent_name.replace("_", " ").title()
                header_text = f"⚡ {friendly_cmd}"
                if desc:
                    header_text += f" — {desc}"
                cmd_title = StrongBodyLabel(header_text, self.details_container)
                cmd_title.setStyleSheet("color: #0078d4;")
                cmd_box.addWidget(cmd_title)

                # 2. Voice Examples Subitem (indented)
                if phrases:
                    subitem_box = QHBoxLayout()
                    subitem_box.setContentsMargins(18, 0, 0, 0)
                    subitem_box.setSpacing(6)

                    phrases_str = " • ".join(f'"{p}"' for p in phrases[:4])
                    if len(phrases) > 4:
                        phrases_str += f" (+{len(phrases) - 4} mais)"

                    subitem_label = CaptionLabel(
                        f"└ 🎙️ Exemplos de voz: {phrases_str}",
                        self.details_container,
                    )
                    subitem_label.setStyleSheet(
                        "color: rgba(220, 220, 220, 0.7); font-style: italic;"
                    )
                    subitem_box.addWidget(subitem_label)
                    subitem_box.addStretch(1)

                    cmd_box.addLayout(subitem_box)

                details_layout.addLayout(cmd_box)
        else:
            no_cmds = CaptionLabel("Nenhum comando registrado.", self.details_container)
            details_layout.addWidget(no_cmds)

        self._details_expanded = False
        layout.addWidget(self.details_container)

    def _on_switch_changed(self, checked: bool) -> None:
        try:
            plugin_manager.set_plugin_enabled(self.plugin_id, checked)
            status_str = "ativado" if checked else "desativado"
            p_name = self.plugin_info.get("name", self.plugin_id)
            InfoBar.success(
                title="Preset Atualizado",
                content=f"O plugin '{p_name}' foi {status_str}.",
                parent=self.window(),
                duration=2500,
            )
        except Exception as e:
            logger.error(f"Failed to toggle plugin {self.plugin_id}: {e}")
            InfoBar.error(
                title="Erro",
                content=f"Falha ao alterar status do plugin: {e}",
                parent=self.window(),
                duration=3500,
            )

    def _toggle_details(self) -> None:
        self._details_expanded = not self._details_expanded
        self.details_container.setVisible(self._details_expanded)
        self.toggle_details_btn.setText(
            "Ocultar Comandos" if self._details_expanded else "Ver Comandos"
        )


class PluginsTab(QWidget):
    """Tab widget for browsing, enabling, disabling, and managing automation presets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Header Row
        header_widget = QWidget(self)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        self.title_label = SubtitleLabel("Plugins & Presets de Automação", self)
        title_box.addWidget(self.title_label)

        self.subtitle_label = CaptionLabel(
            "Ative ou desative áreas de comandos para personalizar seu assistente sob demanda.",
            self,
        )
        title_box.addWidget(self.subtitle_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch(1)

        # Action Buttons: Reload and Open Folder with Fluent Icons
        self.reload_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.reload_btn.setToolTip("Recarregar plugins do disco")
        self.reload_btn.clicked.connect(self._reload_plugins)
        header_layout.addWidget(self.reload_btn)

        self.open_folder_btn = TransparentToolButton(FluentIcon.FOLDER, self)
        self.open_folder_btn.setToolTip("Abrir pasta de plugins no Windows Explorer")
        self.open_folder_btn.clicked.connect(self._open_plugins_folder)
        header_layout.addWidget(self.open_folder_btn)

        main_layout.addWidget(header_widget)

        # Scroll Area for Cards
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 8, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area)

        # Populate cards initially
        self._populate_plugin_cards()

        # Listen for external plugin changes
        plugin_manager.register_change_listener(self._on_external_change)

    def _open_plugins_folder(self) -> None:
        """Opens the plugins directory in Windows Explorer."""
        folder_path = Path(plugin_manager.plugins_dir).resolve()
        folder_path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_path)))

    def _reload_plugins(self) -> None:
        """Reloads plugin files from disk and refreshes the cards."""
        plugin_manager.load_plugins()
        self._populate_plugin_cards()
        InfoBar.info(
            title="Plugins Recarregados",
            content=f"{len(plugin_manager.get_available_plugins())} plugins encontrados.",
            parent=self.window(),
            duration=2000,
        )

    def _on_external_change(self) -> None:
        """Handler for when plugin configuration changes externally."""
        pass

    def _populate_plugin_cards(self) -> None:
        """Clears and re-creates all plugin cards based on currently available plugins."""
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        plugins = plugin_manager.get_available_plugins()
        if not plugins:
            empty_label = BodyLabel(
                "Nenhum plugin encontrado na pasta 'plugins/'.", self
            )
            self.cards_layout.addWidget(empty_label)
            return

        for p_info in plugins:
            card = PluginCard(p_info, self.cards_container)
            self.cards_layout.addWidget(card)
