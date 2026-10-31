import re
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    InfoBar,
    PasswordLineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SegmentedWidget,
    SimpleCardWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    SwitchButton,
    TransparentToolButton,
)
from qfluentwidgets import (
    LineEdit as FluentLineEdit,
)

from core.ai.llm_agent import llm_agent
from core.infra.config import (
    config,
    update_yaml_active_provider,
    update_yaml_bool_setting,
    update_yaml_performance_profile,
    update_yaml_str_setting,
    update_yaml_ui_position,
    update_yaml_weather_city,
)
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.infra.presets import detect_recommended_preset, get_system_hardware_info
from core.infra.update_preferences import UpdatePreferenceManager
from core.infra.updater import ReleaseInfo, UpdateManager
from core.shared.constants import DEFAULT_PROVIDER
from core.shared.paths import get_app_version, get_user_config_path
from core.shared.utils import is_autostart_enabled_check, manage_autostart
from core.ui.screen_position import SCREEN_POSITION_LABELS, SCREEN_POSITIONS_ORDER
from core.ui.widgets.hotkey_recorder import HotkeyRecorder


class MiniMonitorPreview(QFrame):
    """Minimalist interactive mini-monitor widget (Option B) for selecting screen position."""

    position_selected = Signal(str)

    def __init__(
        self, initial_position: str = "top_center", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MiniMonitorFrame")
        self.setFixedSize(172, 108)
        self._selected = (
            initial_position
            if initial_position in SCREEN_POSITIONS_ORDER
            else "top_center"
        )
        self.spot_buttons: dict[str, QPushButton] = {}

        self.setStyleSheet(
            """
            QFrame#MiniMonitorFrame {
                background-color: #101014;
                border: 2px solid #2e2e38;
                border-radius: 8px;
            }
            """
        )

        grid = QGridLayout(self)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(4)

        positions_grid = [
            ("top_left", 0, 0),
            ("top_center", 0, 1),
            ("top_right", 0, 2),
            ("center", 1, 1),
            ("bottom_left", 2, 0),
            ("bottom_center", 2, 1),
            ("bottom_right", 2, 2),
        ]

        for pos_key, row, col in positions_grid:
            btn = QPushButton(self)
            btn.setFixedSize(40, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(SCREEN_POSITION_LABELS.get(pos_key, pos_key))
            btn.clicked.connect(
                lambda checked=False, k=pos_key: self.set_selected_position(k)
            )
            self.spot_buttons[pos_key] = btn
            grid.addWidget(btn, row, col, Qt.AlignmentFlag.AlignCenter)

        # Placeholder label for row 1 col 0 and row 1 col 2 to keep layout balanced
        for r, c in [(1, 0), (1, 2)]:
            empty_lbl = QLabel(self)
            empty_lbl.setFixedSize(40, 22)
            grid.addWidget(empty_lbl, r, c)

        self._refresh_styles()

    def set_selected_position(self, pos_key: str, emit_signal: bool = True) -> None:
        if pos_key in SCREEN_POSITIONS_ORDER and self._selected != pos_key:
            self._selected = pos_key
            self._refresh_styles()
            if emit_signal:
                self.position_selected.emit(pos_key)

    def _refresh_styles(self) -> None:
        selected_style = """
            QPushButton {
                background-color: #0078d4;
                border: 1px solid #2893ea;
                border-radius: 4px;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
            }
        """
        normal_style = """
            QPushButton {
                background-color: #1f1f26;
                border: 1px solid #33333f;
                border-radius: 4px;
                color: #6c6c7d;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #2b2b36;
                border-color: #4b4b5c;
                color: #cccccc;
            }
        """
        for k, btn in self.spot_buttons.items():
            btn.setStyleSheet(selected_style if k == self._selected else normal_style)
            btn.setText("●" if k == self._selected else "")


class SettingsTab(QWidget):
    """Refined Settings tab organized into 3 clear sub-tabs:

    1. Screen & Voice: Position preview, hotkeys & wake word, audio & risk toggles.
    2. AI & Tools: Provider selector, API keys, AI proactivity, response phrase, web search, weather.
    3. System: Hardware performance profile, autostart, updates.
    """

    autostart_toggled = Signal(bool)
    provider_changed = Signal(str)
    restart_requested = Signal()
    update_restart_requested = Signal(Path)
    update_checked = Signal(object)
    update_progress = Signal(int, int)
    update_extracting = Signal()
    update_download_finished = Signal(object)
    update_failed = Signal(str)

    PROFILES_ORDER = [
        "auto",
        "ultra_economic",
        "economic",
        "balanced",
        "performance",
    ]
    PROFILE_LABELS = {
        "auto": "Automático (Detectar Hardware)",
        "ultra_economic": "Ultra Econômico (PC Muito Fraco)",
        "economic": "Econômico (PC Entrada)",
        "balanced": "Equilibrado (Recomendado)",
        "performance": "Alto Desempenho (PC Gamer/Workstation)",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_recorder: HotkeyRecorder | None = None
        self._active_field: str | None = None
        self._prev_recorded_val: str = ""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(10)

        # Header Row (matching PluginsTab style with Action Buttons on top right)
        header_widget = QWidget(self)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 2, 4, 2)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = SubtitleLabel("Configurações do Jarvis", self)
        title_box.addWidget(self.title_label)

        self.subtitle_label = CaptionLabel(
            "Preferências do assistente, posicionamento na tela, atalhos, IA e sistema.",
            self,
        )
        title_box.addWidget(self.subtitle_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch(1)

        # Tool buttons: Open config file and open configuration folder
        self.open_config_btn = TransparentToolButton(FluentIcon.DOCUMENT, header_widget)
        self.open_config_btn.setToolTip("Abrir config.yaml no editor padrão")
        self.open_config_btn.clicked.connect(self._open_config_file)
        header_layout.addWidget(self.open_config_btn)

        self.open_folder_btn = TransparentToolButton(FluentIcon.FOLDER, header_widget)
        self.open_folder_btn.setToolTip(
            "Abrir pasta de configuração no Windows Explorer"
        )
        self.open_folder_btn.clicked.connect(self._open_config_folder)
        header_layout.addWidget(self.open_folder_btn)

        main_layout.addWidget(header_widget)

        # Sub-navigation bar (3 clickable sub-tabs without horizontal clutter)
        self.sub_pivot = SegmentedWidget(self)
        self.sub_stack = QStackedWidget(self)

        self.pane_ui_voice = QWidget(self)
        self.pane_ai_keys = QWidget(self)
        self.pane_sys_upd = QWidget(self)

        self._build_pane_ui_voice()
        self._build_pane_ai_keys()
        self._build_pane_sys_upd()

        self._add_sub_tab(self.pane_ui_voice, "ui_voice", "🖥️ Tela & Voz")
        self._add_sub_tab(self.pane_ai_keys, "ai_keys", "🧠 IA & Ferramentas")
        self._add_sub_tab(self.pane_sys_upd, "sys_upd", "🔄 Sistema")

        self.sub_pivot.setCurrentItem("ui_voice")
        self.sub_stack.setCurrentWidget(self.pane_ui_voice)

        main_layout.addWidget(self.sub_pivot)
        main_layout.addWidget(self.sub_stack, 1)

    def _add_sub_tab(self, widget: QWidget, route_key: str, text: str) -> None:
        self.sub_stack.addWidget(widget)
        self.sub_pivot.addItem(
            routeKey=route_key,
            text=text,
            onClick=lambda: self.sub_stack.setCurrentWidget(widget),
        )

    def _style_card(self, card: SimpleCardWidget) -> None:
        card.setStyleSheet(
            """
            SimpleCardWidget {
                background-color: #19191d;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 9px;
            }
            """
        )

    # ------------------------------------------------------------------
    # Sub-Tab 1: 🖥️ Screen & Voice (Screen Position, Hotkeys & Wake Keyword, Toggles)
    # ------------------------------------------------------------------
    def _build_pane_ui_voice(self) -> None:
        pane_layout = QVBoxLayout(self.pane_ui_voice)
        pane_layout.setContentsMargins(0, 0, 0, 0)

        scroll = SmoothScrollArea(self.pane_ui_voice)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 2, 4, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Card 1: Screen Position (Option B: Mini-Monitor + Selectors)
        pos_card = SimpleCardWidget(scroll_content)
        self._style_card(pos_card)
        pos_layout = QVBoxLayout(pos_card)
        pos_layout.setContentsMargins(16, 12, 16, 12)
        pos_layout.setSpacing(8)

        pos_title = StrongBodyLabel("📍 Posição na Tela", pos_card)
        pos_layout.addWidget(pos_title)

        pos_desc = CaptionLabel(
            "Clique no monitor ou selecione na lista onde exibir cada janela flutuante.",
            pos_card,
        )
        pos_desc.setStyleSheet("color: #82828e;")
        pos_layout.addWidget(pos_desc)

        split_row = QHBoxLayout()
        split_row.setSpacing(12)

        ui_cfg = config.get("ui", {})
        cur_conf_pos = ui_cfg.get("confirmation_position", "top_center")
        cur_hud_pos = ui_cfg.get("voice_hud_position", "bottom_center")

        self.mini_monitor = MiniMonitorPreview(cur_conf_pos, pos_card)
        self.mini_monitor.position_selected.connect(
            self._on_mini_monitor_position_selected
        )
        split_row.addWidget(self.mini_monitor)

        selectors_col = QVBoxLayout()
        selectors_col.setSpacing(10)

        # Row A: Confirmation Dialog Position
        conf_row = QHBoxLayout()
        conf_row.setSpacing(8)
        conf_text_col = QVBoxLayout()
        conf_text_col.setSpacing(1)
        conf_lbl = BodyLabel("Confirmação de Comandos", pos_card)
        conf_sub = CaptionLabel("Card de autorização de risco", pos_card)
        conf_sub.setStyleSheet("color: #777784;")
        conf_text_col.addWidget(conf_lbl)
        conf_text_col.addWidget(conf_sub)
        conf_row.addLayout(conf_text_col, 1)

        self.confirmation_pos_combo = ComboBox(pos_card)
        self.confirmation_pos_combo.addItems(
            [SCREEN_POSITION_LABELS[k] for k in SCREEN_POSITIONS_ORDER]
        )
        if cur_conf_pos in SCREEN_POSITIONS_ORDER:
            self.confirmation_pos_combo.setCurrentIndex(
                SCREEN_POSITIONS_ORDER.index(cur_conf_pos)
            )
        self.confirmation_pos_combo.currentIndexChanged.connect(
            self._on_confirmation_combo_changed
        )
        self.confirmation_pos_combo.setFixedWidth(190)
        conf_row.addWidget(self.confirmation_pos_combo)
        selectors_col.addLayout(conf_row)

        # Row B: Voice HUD Position
        hud_row = QHBoxLayout()
        hud_row.setSpacing(8)
        hud_text_col = QVBoxLayout()
        hud_text_col.setSpacing(1)
        hud_lbl = BodyLabel("Painel HUD de Voz", pos_card)
        hud_sub = CaptionLabel("Onda sonora e transcrição ativa", pos_card)
        hud_sub.setStyleSheet("color: #777784;")
        hud_text_col.addWidget(hud_lbl)
        hud_text_col.addWidget(hud_sub)
        hud_row.addLayout(hud_text_col, 1)

        self.hud_pos_combo = ComboBox(pos_card)
        self.hud_pos_combo.addItems(
            [SCREEN_POSITION_LABELS[k] for k in SCREEN_POSITIONS_ORDER]
        )
        if cur_hud_pos in SCREEN_POSITIONS_ORDER:
            self.hud_pos_combo.setCurrentIndex(
                SCREEN_POSITIONS_ORDER.index(cur_hud_pos)
            )
        self.hud_pos_combo.currentIndexChanged.connect(self._on_hud_combo_changed)
        self.hud_pos_combo.setFixedWidth(190)
        hud_row.addWidget(self.hud_pos_combo)
        selectors_col.addLayout(hud_row)

        split_row.addLayout(selectors_col, 1)
        pos_layout.addLayout(split_row)
        layout.addWidget(pos_card)

        # Card 2: Hotkeys & Wake Word Keyword
        keys_card = SimpleCardWidget(scroll_content)
        self._style_card(keys_card)
        keys_layout = QVBoxLayout(keys_card)
        keys_layout.setContentsMargins(16, 12, 16, 12)
        keys_layout.setSpacing(10)

        keys_title = StrongBodyLabel("⌨️ Atalhos & Palavra de Ativação", keys_card)
        keys_layout.addWidget(keys_title)

        keys_desc = CaptionLabel(
            "Configure a palavra de ativação e os atalhos de teclado globais.",
            keys_card,
        )
        keys_desc.setStyleSheet("color: #82828e;")
        keys_layout.addWidget(keys_desc)

        # Row 1: Wake Word Keyword
        kw_row = QHBoxLayout()
        kw_row.setSpacing(8)
        kw_lbl = BodyLabel("Palavra de Ativação:", keys_card)
        kw_lbl.setFixedWidth(155)
        kw_row.addWidget(kw_lbl)

        self.wake_keyword_input = FluentLineEdit(keys_card)
        current_kw = (
            config.get("voice_activation", {})
            .get("wake_word", {})
            .get("keyword", "hey_jarvis")
        )
        self.wake_keyword_input.setText(str(current_kw))
        self.wake_keyword_input.setPlaceholderText("Ex: hey_jarvis")
        self.wake_keyword_input.setToolTip(
            "Nome do modelo treinado (ONNX) na pasta models/. Espaços são convertidos em underline."
        )
        self.wake_keyword_input.setClearButtonEnabled(True)
        self.wake_keyword_input.textChanged.connect(self._on_wake_keyword_changed)
        kw_row.addWidget(self.wake_keyword_input, 1)
        keys_layout.addLayout(kw_row)

        # Row 2: Push-to-Talk Hotkey & Behavior
        ptt_row = QHBoxLayout()
        ptt_row.setSpacing(8)
        ptt_lbl = BodyLabel("Push-to-Talk (Atalho):", keys_card)
        ptt_lbl.setFixedWidth(155)
        ptt_row.addWidget(ptt_lbl)

        self.ptt_key_input = FluentLineEdit(keys_card)
        cur_ptt_key = (
            config.get("voice_activation", {})
            .get("push_to_talk", {})
            .get("key", "ctrl+alt")
        )
        self.ptt_key_input.setText(str(cur_ptt_key))
        self.ptt_key_input.setPlaceholderText("Ex: ctrl+alt")
        self.ptt_key_input.setClearButtonEnabled(True)
        ptt_row.addWidget(self.ptt_key_input, 1)

        self.ptt_record_btn = PushButton("⏺ Gravar", keys_card)
        self.ptt_record_btn.setFixedWidth(115)
        self.ptt_record_btn.setToolTip(
            "Gravar combinação física de teclas (5 segundos)"
        )
        self.ptt_record_btn.clicked.connect(
            lambda: self._toggle_hotkey_recording("ptt")
        )
        ptt_row.addWidget(self.ptt_record_btn)

        self.ptt_behavior_combo = ComboBox(keys_card)
        self.ptt_behavior_combo.addItems(["Segurar (Hold)", "Alternar (Toggle)"])
        cur_ptt_beh = (
            config.get("voice_activation", {})
            .get("push_to_talk", {})
            .get("behavior", "hold")
        )
        self.ptt_behavior_combo.setCurrentIndex(1 if cur_ptt_beh == "toggle" else 0)
        self.ptt_behavior_combo.setFixedWidth(150)
        ptt_row.addWidget(self.ptt_behavior_combo)
        keys_layout.addLayout(ptt_row)

        # Row 3: Command Palette Hotkey
        cp_row = QHBoxLayout()
        cp_row.setSpacing(8)
        cp_lbl = BodyLabel("Paleta de Comandos:", keys_card)
        cp_lbl.setFixedWidth(155)
        cp_row.addWidget(cp_lbl)

        self.command_palette_key_input = FluentLineEdit(keys_card)
        cur_cp_key = config.get("command_palette", {}).get("key", "ctrl+shift+p")
        self.command_palette_key_input.setText(str(cur_cp_key))
        self.command_palette_key_input.setPlaceholderText("Ex: ctrl+shift+p")
        self.command_palette_key_input.setClearButtonEnabled(True)
        cp_row.addWidget(self.command_palette_key_input, 1)

        self.cp_record_btn = PushButton("⏺ Gravar", keys_card)
        self.cp_record_btn.setFixedWidth(115)
        self.cp_record_btn.setToolTip("Gravar combinação física de teclas (5 segundos)")
        self.cp_record_btn.clicked.connect(
            lambda: self._toggle_hotkey_recording("command_palette")
        )
        cp_row.addWidget(self.cp_record_btn)
        keys_layout.addLayout(cp_row)

        # Save shortcuts button
        save_keys_row = QHBoxLayout()
        save_keys_row.addStretch(1)
        self.save_shortcuts_btn = PrimaryPushButton("Salvar Atalhos", keys_card)
        self.save_shortcuts_btn.setFixedWidth(160)
        self.save_shortcuts_btn.clicked.connect(self._save_shortcuts)
        save_keys_row.addWidget(self.save_shortcuts_btn)
        keys_layout.addLayout(save_keys_row)

        layout.addWidget(keys_card)

        # Card 3: Behavior Toggles (Uniform Switch Alignment)
        beh_card = SimpleCardWidget(scroll_content)
        self._style_card(beh_card)
        beh_layout = QVBoxLayout(beh_card)
        beh_layout.setContentsMargins(16, 12, 16, 12)
        beh_layout.setSpacing(10)

        beh_title = StrongBodyLabel("🎙️ Voz & Comportamento", beh_card)
        beh_layout.addWidget(beh_title)

        # Audio Cues Switch
        cues_row = QHBoxLayout()
        cues_row.addWidget(
            BodyLabel("Efeitos Sonoros (Beeps ao ativar/concluir):", beh_card),
            1,
        )
        self.audio_cues_switch = SwitchButton(beh_card)
        self.audio_cues_switch.setOnText("Ativo")
        self.audio_cues_switch.setOffText("Inativo")
        self.audio_cues_switch.setFixedWidth(102)
        self.audio_cues_switch.setChecked(
            bool(config.get("audio_cues", {}).get("enabled", True))
        )
        self.audio_cues_switch.checkedChanged.connect(self._on_audio_cues_toggled)
        cues_row.addWidget(self.audio_cues_switch)
        beh_layout.addLayout(cues_row)

        # Fullscreen Auto-Suspend Switch
        fs_row = QHBoxLayout()
        fs_row.addWidget(
            BodyLabel("Suspender automaticamente em Jogos / Tela Cheia:", beh_card),
            1,
        )
        self.fullscreen_suspend_switch = SwitchButton(beh_card)
        self.fullscreen_suspend_switch.setOnText("Ativo")
        self.fullscreen_suspend_switch.setOffText("Inativo")
        self.fullscreen_suspend_switch.setFixedWidth(102)
        self.fullscreen_suspend_switch.setChecked(
            bool(
                config.get("voice_activation", {})
                .get("auto_suspend", {})
                .get("fullscreen", True)
            )
        )
        self.fullscreen_suspend_switch.checkedChanged.connect(
            self._on_fullscreen_suspend_toggled
        )
        fs_row.addWidget(self.fullscreen_suspend_switch)
        beh_layout.addLayout(fs_row)

        # Dry-Run Risk Confirmation Switch
        dry_row = QHBoxLayout()
        dry_row.addWidget(
            BodyLabel("Pedir confirmação na tela para ações de risco:", beh_card),
            1,
        )
        self.dry_run_switch = SwitchButton(beh_card)
        self.dry_run_switch.setOnText("Ativo")
        self.dry_run_switch.setOffText("Inativo")
        self.dry_run_switch.setFixedWidth(102)
        self.dry_run_switch.setChecked(
            bool(config.get("dry_run", {}).get("enabled", True))
        )
        self.dry_run_switch.checkedChanged.connect(self._on_dry_run_toggled)
        dry_row.addWidget(self.dry_run_switch)
        beh_layout.addLayout(dry_row)

        layout.addWidget(beh_card)

        scroll.setWidget(scroll_content)
        pane_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Sub-Tab 2: 🧠 AI & Tools (API Keys, Proactivity, Response Phrase, Web Search, Weather)
    # ------------------------------------------------------------------
    def _build_pane_ai_keys(self) -> None:
        pane_layout = QVBoxLayout(self.pane_ai_keys)
        pane_layout.setContentsMargins(0, 0, 0, 0)

        scroll = SmoothScrollArea(self.pane_ai_keys)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 2, 4, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Card 1: Provider & Keys
        provider_card = SimpleCardWidget(scroll_content)
        self._style_card(provider_card)
        provider_layout = QVBoxLayout(provider_card)
        provider_layout.setContentsMargins(16, 14, 16, 14)
        provider_layout.setSpacing(12)

        provider_title = StrongBodyLabel(
            "🔑 Provedor de Inteligência Artificial", provider_card
        )
        provider_layout.addWidget(provider_title)

        # Row 1: Provider Selector + Primary Action Button
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        prov_lbl = BodyLabel("Provedor:", provider_card)
        prov_lbl.setFixedWidth(85)
        prov_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row1.addWidget(prov_lbl)

        self.provider_combo = ComboBox(provider_card)
        self.providers = [
            "gemini",
            "openai",
            "anthropic",
            "deepseek",
            "openrouter",
        ]
        self.provider_combo.addItems([p.capitalize() for p in self.providers])
        active = config.get("llm", {}).get("active_provider", DEFAULT_PROVIDER)
        if active in self.providers:
            self.provider_combo.setCurrentIndex(self.providers.index(active))
        row1.addWidget(self.provider_combo, 1)

        self.set_active_btn = PrimaryPushButton("Definir como Ativo", provider_card)
        self.set_active_btn.setFixedWidth(170)
        self.set_active_btn.clicked.connect(self._set_active_provider)
        row1.addWidget(self.set_active_btn)
        provider_layout.addLayout(row1)

        # Row 2: API Key LineEdit + Save Action Button
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        key_lbl = BodyLabel("Nova Chave:", provider_card)
        key_lbl.setFixedWidth(85)
        key_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row2.addWidget(key_lbl)

        self.api_key_input = PasswordLineEdit(provider_card)
        self.api_key_input.setPlaceholderText("Cole sua chave de API aqui...")
        self.api_key_input.setClearButtonEnabled(True)
        row2.addWidget(self.api_key_input, 1)

        self.save_key_btn = PrimaryPushButton("Salvar Chave", provider_card)
        self.save_key_btn.setFixedWidth(170)
        self.save_key_btn.clicked.connect(self._save_key)
        row2.addWidget(self.save_key_btn)
        provider_layout.addLayout(row2)

        # Row 3: Validate Key Secondary Action Button
        row3 = QHBoxLayout()
        row3.setSpacing(10)
        dummy_indent = QLabel(provider_card)
        dummy_indent.setFixedWidth(85)
        dummy_indent.setStyleSheet("background: transparent;")
        row3.addWidget(dummy_indent)

        self.check_key_btn = PushButton("Validar Chave do Provedor", provider_card)
        self.check_key_btn.clicked.connect(self._validate_key)
        row3.addWidget(self.check_key_btn)
        row3.addStretch(1)
        provider_layout.addLayout(row3)

        key_info = CaptionLabel(
            "🔒 As chaves são armazenadas com criptografia segura no Gerenciador de Credenciais do Windows (Keyring).",
            provider_card,
        )
        key_info.setWordWrap(True)
        key_info.setStyleSheet("color: rgba(200, 200, 200, 0.7);")
        provider_layout.addWidget(key_info)

        layout.addWidget(provider_card)

        # Card 2: AI Personality, Response & Tools
        ai_card = SimpleCardWidget(scroll_content)
        self._style_card(ai_card)
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(16, 14, 16, 14)
        ai_layout.setSpacing(10)

        ai_title = StrongBodyLabel("🤖 Personalidade & Ferramentas da IA", ai_card)
        ai_layout.addWidget(ai_title)

        ai_desc = CaptionLabel(
            "Ajuste a postura do assistente, frase de resposta, buscador na web e localização.",
            ai_card,
        )
        ai_desc.setStyleSheet("color: #82828e;")
        ai_layout.addWidget(ai_desc)

        # Proactivity row
        pro_row = QHBoxLayout()
        pro_row.setSpacing(8)
        pro_lbl = BodyLabel("Proatividade da IA:", ai_card)
        pro_lbl.setFixedWidth(155)
        pro_row.addWidget(pro_lbl)

        self.proactivity_combo = ComboBox(ai_card)
        self.proactivity_options = ["objective", "proactive"]
        self.proactivity_combo.addItems(
            [
                "Objetivo (Direto e conciso)",
                "Proativo (Sugere recomendações práticas)",
            ]
        )
        cur_proact = config.get("ai", {}).get("proactivity", "objective")
        self.proactivity_combo.setCurrentIndex(1 if cur_proact == "proactive" else 0)
        pro_row.addWidget(self.proactivity_combo, 1)
        ai_layout.addLayout(pro_row)

        # Response Phrase row
        resp_row = QHBoxLayout()
        resp_row.setSpacing(8)
        resp_lbl = BodyLabel("Frase de Resposta:", ai_card)
        resp_lbl.setFixedWidth(155)
        resp_row.addWidget(resp_lbl)

        self.response_phrase_input = FluentLineEdit(ai_card)
        cur_phrase = config.get("voice_activation", {}).get("response_phrase", "Sim?")
        self.response_phrase_input.setText(str(cur_phrase))
        self.response_phrase_input.setPlaceholderText("Ex: Sim?, Às ordens!")
        self.response_phrase_input.setClearButtonEnabled(True)
        resp_row.addWidget(self.response_phrase_input, 1)
        ai_layout.addLayout(resp_row)

        # Web search provider row
        ws_row = QHBoxLayout()
        ws_row.setSpacing(8)
        ws_lbl = BodyLabel("Buscador Web:", ai_card)
        ws_lbl.setFixedWidth(155)
        ws_row.addWidget(ws_lbl)

        self.web_search_combo = ComboBox(ai_card)
        self.web_search_options = ["duckduckgo", "tavily"]
        self.web_search_combo.addItems(
            [
                "DuckDuckGo (Gratuito e sem chave)",
                "Tavily (API de Busca LLM)",
            ]
        )
        cur_ws = (
            config.get("tools", {}).get("web_search", {}).get("provider", "duckduckgo")
        )
        self.web_search_combo.setCurrentIndex(1 if cur_ws == "tavily" else 0)
        ws_row.addWidget(self.web_search_combo, 1)
        ai_layout.addLayout(ws_row)

        # Default Weather Location row
        loc_row = QHBoxLayout()
        loc_row.setSpacing(8)
        loc_lbl = BodyLabel("Cidade Padrão (Clima):", ai_card)
        loc_lbl.setFixedWidth(155)
        loc_row.addWidget(loc_lbl)

        self.city_input = FluentLineEdit(ai_card)
        self.city_input.setPlaceholderText("Ex: São Paulo, Itamonte, Curitiba...")
        self.city_input.setClearButtonEnabled(True)
        cur_city = (
            config.get("tools", {}).get("weather", {}).get("default_city", "São Paulo")
        )
        self.city_input.setText(str(cur_city))
        loc_row.addWidget(self.city_input, 1)
        ai_layout.addLayout(loc_row)

        # Save AI preferences button (also aliases save_city_btn for backwards compatibility)
        save_ai_row = QHBoxLayout()
        save_ai_row.addStretch(1)
        self.save_city_btn = PrimaryPushButton("Salvar Preferências da IA", ai_card)
        self.save_city_btn.setFixedWidth(190)
        self.save_city_btn.clicked.connect(self._save_ai_preferences)
        save_ai_row.addWidget(self.save_city_btn)
        ai_layout.addLayout(save_ai_row)

        layout.addWidget(ai_card)

        scroll.setWidget(scroll_content)
        pane_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Sub-Tab 3: 🔄 System (Performance Profile, Autostart, Updates)
    # ------------------------------------------------------------------
    def _build_pane_sys_upd(self) -> None:
        pane_layout = QVBoxLayout(self.pane_sys_upd)
        pane_layout.setContentsMargins(0, 0, 0, 0)

        # Smooth scrolling container to accommodate system configuration sections
        self.sys_scroll = SmoothScrollArea(self.pane_sys_upd)
        self.sys_scroll.setWidgetResizable(True)
        self.sys_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sys_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sys_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 2, 4, 8)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Card 1: Performance Profile
        perf_card = SimpleCardWidget(scroll_content)
        self._style_card(perf_card)
        perf_layout = QVBoxLayout(perf_card)
        perf_layout.setContentsMargins(16, 12, 16, 12)
        perf_layout.setSpacing(8)

        perf_title = StrongBodyLabel("⚡ Perfil de Desempenho do Sistema", perf_card)
        perf_layout.addWidget(perf_title)

        self.slider_label = BodyLabel(perf_card)
        perf_layout.addWidget(self.slider_label)

        self.slider = QSlider(Qt.Orientation.Horizontal, perf_card)
        self.slider.setRange(0, 4)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(1)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)

        current_prof = config.get("performance_profile", "auto")
        if current_prof in self.PROFILES_ORDER:
            self.slider.setValue(self.PROFILES_ORDER.index(current_prof))
        else:
            self.slider.setValue(0)

        perf_layout.addWidget(self.slider)

        self.desc_label = CaptionLabel(perf_card)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #9a9aa6;")
        perf_layout.addWidget(self.desc_label)

        self.apply_btn = PrimaryPushButton("Aplicar e Reiniciar Jarvis", perf_card)
        self.apply_btn.setVisible(False)
        self.apply_btn.clicked.connect(self._apply_and_restart)
        perf_layout.addWidget(self.apply_btn)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self._update_slider_text(self.slider.value())

        layout.addWidget(perf_card)

        # Card 2: Windows Autostart (Clean card without duplicate file icons)
        sys_card = SimpleCardWidget(scroll_content)
        self._style_card(sys_card)
        sys_layout = QVBoxLayout(sys_card)
        sys_layout.setContentsMargins(16, 14, 16, 14)
        sys_layout.setSpacing(10)

        sys_title = StrongBodyLabel("🪟 Inicialização do Sistema", sys_card)
        sys_layout.addWidget(sys_title)

        auto_row = QHBoxLayout()
        auto_row.addWidget(
            BodyLabel("Iniciar o Jarvis junto com o Windows:", sys_card), 1
        )
        self.autostart_switch = SwitchButton(sys_card)
        self.autostart_switch.setOnText("Ativo")
        self.autostart_switch.setOffText("Inativo")
        self.autostart_switch.setFixedWidth(102)
        self.autostart_switch.setChecked(is_autostart_enabled_check())
        self.autostart_switch.checkedChanged.connect(self._on_autostart_toggled)
        auto_row.addWidget(self.autostart_switch)
        sys_layout.addLayout(auto_row)

        layout.addWidget(sys_card)

        # Card 3: System Updates
        self.update_mgr = UpdateManager()
        self.pref_mgr = UpdatePreferenceManager()
        self._latest_release: ReleaseInfo | None = None

        self.update_checked.connect(self._on_update_check_finished)
        self.update_progress.connect(self._on_update_progress)
        self.update_extracting.connect(self._on_update_extracting)
        self.update_download_finished.connect(self._on_download_finished)
        self.update_failed.connect(self._on_update_failed)

        update_card = SimpleCardWidget(scroll_content)
        self._style_card(update_card)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(16, 12, 16, 12)
        update_layout.setSpacing(8)

        update_title = StrongBodyLabel("🔄 Atualizações do Sistema", update_card)
        update_layout.addWidget(update_title)

        self.version_label = BodyLabel(
            f"<b>Versão Instalada:</b> v{get_app_version()}", update_card
        )
        update_layout.addWidget(self.version_label)

        self.update_status_label = CaptionLabel(
            "Nenhuma verificação recente realizada.", update_card
        )
        self.update_status_label.setWordWrap(True)
        update_layout.addWidget(self.update_status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.check_update_btn = PushButton("Verificar Atualizações", update_card)
        self.check_update_btn.clicked.connect(self._on_check_update_clicked)
        btn_row.addWidget(self.check_update_btn)

        self.apply_update_btn = PrimaryPushButton("Baixar e Atualizar", update_card)
        self.apply_update_btn.setVisible(False)
        self.apply_update_btn.clicked.connect(self._download_and_apply_update)
        btn_row.addWidget(self.apply_update_btn)

        self.snooze_btn = PushButton("Lembrar Mais Tarde", update_card)
        self.snooze_btn.setVisible(False)
        self.snooze_btn.clicked.connect(self._on_snooze_clicked)
        btn_row.addWidget(self.snooze_btn)
        btn_row.addStretch(1)
        update_layout.addLayout(btn_row)

        self.update_progress_bar = ProgressBar(update_card)
        self.update_progress_bar.setVisible(False)
        update_layout.addWidget(self.update_progress_bar)

        layout.addWidget(update_card)

        self.sys_scroll.setWidget(scroll_content)
        pane_layout.addWidget(self.sys_scroll)

    # ------------------------------------------------------------------
    # Handlers for Screen Position & Toggles
    # ------------------------------------------------------------------
    def _on_mini_monitor_position_selected(self, pos_key: str) -> None:
        if pos_key in SCREEN_POSITIONS_ORDER:
            idx = SCREEN_POSITIONS_ORDER.index(pos_key)
            if self.confirmation_pos_combo.currentIndex() != idx:
                self.confirmation_pos_combo.blockSignals(True)
                self.confirmation_pos_combo.setCurrentIndex(idx)
                self.confirmation_pos_combo.blockSignals(False)
        self._save_ui_position("confirmation_position", pos_key)

    def _on_confirmation_combo_changed(self, index: int) -> None:
        if 0 <= index < len(SCREEN_POSITIONS_ORDER):
            pos_key = SCREEN_POSITIONS_ORDER[index]
            self.mini_monitor.set_selected_position(pos_key, emit_signal=False)
            self._save_ui_position("confirmation_position", pos_key)

    def _on_hud_combo_changed(self, index: int) -> None:
        if 0 <= index < len(SCREEN_POSITIONS_ORDER):
            pos_key = SCREEN_POSITIONS_ORDER[index]
            self._save_ui_position("voice_hud_position", pos_key)

    def _save_ui_position(self, key_name: str, pos_key: str) -> None:
        config.setdefault("ui", {})[key_name] = pos_key
        try:
            update_yaml_ui_position(key_name, pos_key)
        except Exception as e:
            logger.warning(f"Could not persist {key_name} to yaml: {e}")

    def _on_wake_keyword_changed(self, text: str) -> None:
        """Converts spaces to underscores automatically while typing."""
        if " " in text:
            pos = self.wake_keyword_input.cursorPosition()
            sanitized = text.replace(" ", "_")
            self.wake_keyword_input.blockSignals(True)
            self.wake_keyword_input.setText(sanitized)
            self.wake_keyword_input.setCursorPosition(pos)
            self.wake_keyword_input.blockSignals(False)

    @property
    def wake_keyword_combo(self) -> Any:
        """Compatibility shim for tests and external callers expecting a combobox interface."""

        class _ComboShim:
            def __init__(self, le: FluentLineEdit) -> None:
                self._le = le

            def currentText(self) -> str:  # noqa: N802
                return str(self._le.text())

            def setCurrentText(self, text: str) -> None:  # noqa: N802
                self._le.setText(text)

        return _ComboShim(self.wake_keyword_input)

    def _save_shortcuts(self) -> None:
        raw_kw = self.wake_keyword_input.text().strip().lower()
        kw = re.sub(r"\s+", "_", raw_kw).strip("_") or "hey_jarvis"
        self.wake_keyword_input.setText(kw)
        ptt_key = self.ptt_key_input.text().strip().lower() or "ctrl+alt"
        ptt_beh = "toggle" if self.ptt_behavior_combo.currentIndex() == 1 else "hold"
        cp_key = self.command_palette_key_input.text().strip().lower() or "ctrl+shift+p"

        va = config.setdefault("voice_activation", {})
        va.setdefault("wake_word", {})["keyword"] = kw
        va.setdefault("push_to_talk", {})["key"] = ptt_key
        va.setdefault("push_to_talk", {})["behavior"] = ptt_beh
        config.setdefault("command_palette", {})["key"] = cp_key

        try:
            update_yaml_str_setting(
                "voice_activation", "keyword", kw, subsection="wake_word"
            )
            update_yaml_str_setting(
                "voice_activation", "key", ptt_key, subsection="push_to_talk"
            )
            update_yaml_str_setting(
                "voice_activation",
                "behavior",
                ptt_beh,
                subsection="push_to_talk",
            )
            update_yaml_str_setting("command_palette", "key", cp_key)
        except Exception as e:
            logger.warning(f"Could not persist shortcuts to yaml: {e}")

        try:
            win = self.window()
            if hasattr(win, "parent"):
                parent = win.parent()
                update_fn = (
                    getattr(parent, "update_command_palette_hotkey", None)
                    if parent is not None
                    else None
                )
                if callable(update_fn):
                    update_fn(cp_key)
        except Exception as e:
            logger.debug(f"Could not update app_controller hotkey: {e}")

        InfoBar.success(
            title="Atalhos Salvos",
            content="Atalhos e palavra de ativação atualizados com sucesso!",
            parent=self.window(),
            duration=3000,
        )
        logger.info(
            f"Saved shortcuts: wake_word='{kw}', ptt_key='{ptt_key}', behavior='{ptt_beh}', command_palette='{cp_key}'."
        )

    def _toggle_hotkey_recording(self, field: str) -> None:
        if self._active_recorder and self._active_recorder.is_active:
            same = self._active_field == field
            self._active_recorder.cancel()
            if same:
                return

        self._active_field = field
        if field == "ptt":
            target_input = self.ptt_key_input
            target_btn = self.ptt_record_btn
            self._prev_recorded_val = self.ptt_key_input.text()
        else:
            target_input = self.command_palette_key_input
            target_btn = self.cp_record_btn
            self._prev_recorded_val = self.command_palette_key_input.text()

        target_btn.setText("⏹ Cancelar")
        target_input.setStyleSheet(
            "border: 1.5px solid #0078d4; background-color: #1a2333;"
        )
        target_input.setText("Pressione as teclas... (5s)")

        recorder = HotkeyRecorder(countdown_seconds=5, parent=self)
        self._active_recorder = recorder

        def _on_tick(sec: int) -> None:
            if target_input.text().startswith("Pressione as teclas"):
                target_input.setText(f"Pressione as teclas... ({sec}s)")

        def _on_preview(combo: str) -> None:
            target_input.setText(f"Detectado: {combo}...")

        def _on_captured(combo: str) -> None:
            target_input.setText(combo)
            self._cleanup_recording(target_input, target_btn)
            InfoBar.success(
                title="Atalho Detectado",
                content=f"Atalho definido para '{combo}'. Clique em 'Salvar Atalhos' para aplicar.",
                parent=self.window(),
                duration=3500,
            )

        def _on_cancelled() -> None:
            target_input.setText(self._prev_recorded_val)
            self._cleanup_recording(target_input, target_btn)

        def _on_timeout() -> None:
            target_input.setText(self._prev_recorded_val)
            self._cleanup_recording(target_input, target_btn)
            InfoBar.warning(
                title="Tempo Esgotado",
                content="Nenhuma tecla pressionada nos 5 segundos. Atalho anterior mantido.",
                parent=self.window(),
                duration=3000,
            )

        recorder.tick.connect(_on_tick)
        recorder.live_preview.connect(_on_preview)
        recorder.hotkey_captured.connect(_on_captured)
        recorder.cancelled.connect(_on_cancelled)
        recorder.timeout.connect(_on_timeout)

        recorder.start()

    def _cleanup_recording(
        self, target_input: FluentLineEdit, target_btn: PushButton
    ) -> None:
        target_btn.setText("⏺ Gravar")
        target_input.setStyleSheet("")
        if self._active_recorder:
            self._active_recorder.stop()
            self._active_recorder = None
        self._active_field = None

    def hideEvent(self, event: Any) -> None:  # noqa: N802
        if self._active_recorder and self._active_recorder.is_active:
            self._active_recorder.cancel()
        super().hideEvent(event)

    def _save_ai_preferences(self) -> None:
        proact = self.proactivity_options[self.proactivity_combo.currentIndex()]
        phrase = self.response_phrase_input.text().strip() or "Sim?"
        ws_prov = self.web_search_options[self.web_search_combo.currentIndex()]
        city = self.city_input.text().strip() or "São Paulo"

        config.setdefault("ai", {})["proactivity"] = proact
        config.setdefault("voice_activation", {})["response_phrase"] = phrase
        config.setdefault("tools", {}).setdefault("web_search", {})["provider"] = (
            ws_prov
        )
        config.setdefault("tools", {}).setdefault("weather", {})["default_city"] = city

        try:
            update_yaml_str_setting("ai", "proactivity", proact)
            update_yaml_str_setting("voice_activation", "response_phrase", phrase)
            update_yaml_str_setting(
                "tools", "provider", ws_prov, subsection="web_search"
            )
            update_yaml_weather_city(city)
        except Exception as e:
            logger.warning(f"Could not persist AI preferences to yaml: {e}")

        InfoBar.success(
            title="Preferências Salvas",
            content=f"Configurações de IA salvas com sucesso (Cidade: '{city}', Proatividade: '{proact}').",
            parent=self.window(),
            duration=3000,
        )
        logger.info(
            f"Saved AI preferences: proactivity='{proact}', phrase='{phrase}', web_search='{ws_prov}', city='{city}'."
        )

    def _save_city(self) -> None:
        """Alias for backwards compatibility with tests and callers expecting _save_city."""
        self._save_ai_preferences()

    def _on_audio_cues_toggled(self, checked: bool) -> None:
        config.setdefault("audio_cues", {})["enabled"] = checked
        try:
            update_yaml_bool_setting("audio_cues", "enabled", checked)
        except Exception as e:
            logger.warning(f"Could not persist audio_cues.enabled: {e}")

    def _on_fullscreen_suspend_toggled(self, checked: bool) -> None:
        config.setdefault("voice_activation", {}).setdefault("auto_suspend", {})[
            "fullscreen"
        ] = checked
        try:
            update_yaml_bool_setting(
                "voice_activation",
                "fullscreen",
                checked,
                subsection="auto_suspend",
            )
        except Exception as e:
            logger.warning(f"Could not persist auto_suspend.fullscreen: {e}")

    def _on_dry_run_toggled(self, checked: bool) -> None:
        config.setdefault("dry_run", {})["enabled"] = checked
        try:
            update_yaml_bool_setting("dry_run", "enabled", checked)
        except Exception as e:
            logger.warning(f"Could not persist dry_run.enabled: {e}")

    def _on_autostart_toggled(self, checked: bool) -> None:
        try:
            manage_autostart(enable=checked)
        except Exception as e:
            logger.warning(f"Could not toggle Windows autostart: {e}")
        self.autostart_toggled.emit(checked)

    def set_autostart_state(self, checked: bool) -> None:
        """External sync helper to keep Settings switch aligned with Windows tray state."""
        if (
            hasattr(self, "autostart_switch")
            and self.autostart_switch.isChecked() != checked
        ):
            self.autostart_switch.blockSignals(True)
            self.autostart_switch.setChecked(checked)
            self.autostart_switch.blockSignals(False)

    # ------------------------------------------------------------------
    # Existing Handlers (Files, Performance, Keys, Updates)
    # ------------------------------------------------------------------
    def _open_config_file(self) -> None:
        """Opens the active config.yaml file in the default text editor."""
        try:
            cfg_path = get_user_config_path()
            if cfg_path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(cfg_path.resolve())))
                logger.info(f"Opening config file: {cfg_path}")
            else:
                InfoBar.warning(
                    "Arquivo não encontrado",
                    f"O arquivo {cfg_path.name} não foi encontrado.",
                    parent=self.window(),
                )
        except Exception as e:
            logger.error(f"Failed to open config file: {e}")
            InfoBar.error(
                "Erro",
                f"Não foi possível abrir o arquivo: {e}",
                parent=self.window(),
            )

    def _open_config_folder(self) -> None:
        """Opens the directory containing config.yaml in Windows Explorer."""
        try:
            folder = get_user_config_path().parent.resolve()
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
            logger.info(f"Opening config folder: {folder}")
        except Exception as e:
            logger.error(f"Failed to open config folder: {e}")
            InfoBar.error(
                "Erro",
                f"Não foi possível abrir a pasta: {e}",
                parent=self.window(),
            )

    def _update_slider_text(self, value: int) -> None:
        prof_key = self.PROFILES_ORDER[value]
        hw = get_system_hardware_info()
        resolved = config.get("_resolved_profile", detect_recommended_preset())

        if prof_key == "auto":
            text = f"<b>Perfil Selecionado:</b> Auto (Detectado: <i>{resolved.upper()}</i> - {hw['cpu_cores']} Cores / {hw['ram_gb']:.1f}GB RAM)"
        else:
            text = f"<b>Perfil Selecionado:</b> {self.PROFILE_LABELS[prof_key]}"
        self.slider_label.setText(text)

        descriptions = {
            "auto": "Ajusta dinamicamente as configurações com base no gargalo real de hardware (CPU/RAM).",
            "ultra_economic": "Foco em máquinas antigas/fracas. STT descarrega em 30s, limites estritos de memória e delays conservadores de UI.",
            "economic": "Economia de recursos para PCs de entrada. STT descarrega em 60s e delays moderados.",
            "balanced": "Configuração padrão recomendada com tempo de resposta rápido e descarte de RAM em 180s.",
            "performance": "Velocidade máxima. STT mantido aquecido permanentemente na RAM e delays ultra-rápidos.",
        }
        self.desc_label.setText(descriptions.get(prof_key, ""))

    def _on_slider_changed(self, value: int) -> None:
        self._update_slider_text(value)
        current_prof = config.get("performance_profile", "auto")
        selected_prof = self.PROFILES_ORDER[value]
        self.apply_btn.setVisible(selected_prof != current_prof)

    def _apply_and_restart(self) -> None:
        new_prof = self.PROFILES_ORDER[self.slider.value()]
        try:
            update_yaml_performance_profile(new_prof)
            config["performance_profile"] = new_prof

            InfoBar.success(
                "Configuração Salva",
                "Reiniciando o Jarvis...",
                parent=self,
            )
            self.restart_requested.emit()
        except Exception as e:
            InfoBar.error("Erro", f"Falha ao salvar configuração: {e}", parent=self)

    def _save_key(self) -> None:
        idx = self.provider_combo.currentIndex()
        prov = self.providers[idx]
        key_val = self.api_key_input.text().strip()
        if not key_val:
            InfoBar.warning(
                "Chave Vazia",
                "Por favor, digite ou cole uma chave válida.",
                parent=self,
            )
            return
        secret_name = f"{prov.upper()}_API_KEY"
        KeyringManager.set_secret("python-jarvis", secret_name, key_val)
        self.api_key_input.clear()
        InfoBar.success(
            "Chave Salva",
            f"A chave para {prov.capitalize()} foi salva no Keyring com sucesso!",
            parent=self,
        )

        active_prov = config.get("llm", {}).get("active_provider", DEFAULT_PROVIDER)
        if prov == active_prov:
            try:
                llm_agent.reinit_provider()
                logger.info(
                    f"Reinitialized LLM provider for active provider '{prov}' after key update."
                )
            except Exception as e:
                logger.warning(f"Could not reinitialize LLM provider immediately: {e}")

    def _validate_key(self) -> None:
        idx = self.provider_combo.currentIndex()
        prov = self.providers[idx]
        has_key = KeyringManager.validate_provider_key(prov)
        if has_key:
            InfoBar.success(
                "Chave de API",
                f"A chave para {prov.capitalize()} está configurada.",
                parent=self,
            )
        else:
            InfoBar.warning(
                "Chave de API",
                f"A chave para {prov.capitalize()} não foi configurada.",
                parent=self,
            )

    def _set_active_provider(self) -> None:
        idx = self.provider_combo.currentIndex()
        prov = self.providers[idx]
        has_key = KeyringManager.validate_provider_key(prov)
        if not has_key:
            InfoBar.warning(
                "Chave Não Configurada",
                f"Configure e salve a chave de API para {prov.capitalize()} antes de ativá-lo.",
                parent=self,
            )
            return

        config.setdefault("llm", {})["active_provider"] = prov
        try:
            update_yaml_active_provider(prov)
        except Exception as e:
            logger.warning(f"Could not persist active provider to yaml: {e}")

        try:
            llm_agent.reinit_provider()
            logger.info(f"Active LLM provider switched to '{prov}' via SettingsTab.")
        except Exception as e:
            logger.warning(f"Could not reinitialize LLM provider immediately: {e}")

        self.provider_changed.emit(prov)
        InfoBar.success(
            "Provedor Ativo",
            f"Provedor alterado para {prov.capitalize()}.",
            parent=self,
        )

    def _on_check_update_clicked(self) -> None:
        self.check_update_btn.setEnabled(False)
        self.update_status_label.setText("Buscando atualizações no GitHub...")
        threading.Thread(target=self._check_updates_async, daemon=True).start()

    def _check_updates_async(self) -> None:
        try:
            info = self.update_mgr.check_for_updates()
            self.pref_mgr.record_check()
            self.update_checked.emit(info)
        except Exception as e:
            self.update_failed.emit(str(e))

    def _check_updates_sync(self) -> None:
        """Synchronous check helper used in unit tests."""
        info = self.update_mgr.check_for_updates()
        self.pref_mgr.record_check()
        self._on_update_check_finished(info)

    def _on_update_check_finished(self, info: ReleaseInfo | None) -> None:
        self.check_update_btn.setEnabled(True)
        if info is None:
            self.update_status_label.setText(
                "Não foi possível verificar atualizações (sem conexão com GitHub)."
            )
            self.apply_update_btn.setVisible(False)
            self.snooze_btn.setVisible(False)
            return

        self._latest_release = info
        if info.has_update:
            self.update_status_label.setText(
                f"<b>Nova versão disponível:</b> {info.version} - {info.title}"
            )
            self.apply_update_btn.setText(f"Baixar e Atualizar para {info.version}")
            self.apply_update_btn.setVisible(True)
            self.snooze_btn.setVisible(True)
        else:
            self.update_status_label.setText(
                "Você está usando a versão mais recente do Jarvis!"
            )
            self.apply_update_btn.setVisible(False)
            self.snooze_btn.setVisible(False)

    def _on_snooze_clicked(self) -> None:
        self.pref_mgr.snooze(24.0)
        self.snooze_btn.setVisible(False)
        InfoBar.info(
            "Lembrete Adiado",
            "Aviso de atualização adiado por 24 horas.",
            parent=self,
        )

    def _download_and_apply_update(self) -> None:
        if not self._latest_release or not self._latest_release.download_url:
            InfoBar.warning(
                "Atualização",
                "Nenhum pacote de atualização disponível para download.",
                parent=self,
            )
            return

        self.apply_update_btn.setEnabled(False)
        self.check_update_btn.setEnabled(False)
        self.update_progress_bar.setVisible(True)
        self.update_progress_bar.setValue(0)
        self.update_status_label.setText("Baixando atualização...")

        def _worker() -> None:
            try:

                def _prog(downloaded: int, total: int) -> None:
                    if total > 0:
                        self.update_progress.emit(downloaded, total)

                assert self._latest_release is not None
                zip_path = self.update_mgr.download_asset(
                    self._latest_release.download_url,
                    progress_callback=_prog,
                )
                self.update_extracting.emit()
                extracted = self.update_mgr.extract_archive(zip_path)
                self.update_download_finished.emit(extracted)
            except Exception as exc:
                self.update_failed.emit(str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_update_progress(self, downloaded: int, total: int) -> None:
        pct = int((downloaded / total) * 100) if total > 0 else 0
        self.update_progress_bar.setValue(pct)
        mb_down = downloaded / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        self.update_status_label.setText(
            f"Baixando: {mb_down:.1f}MB / {mb_total:.1f}MB ({pct}%)"
        )

    def _on_update_extracting(self) -> None:
        self.update_status_label.setText("Extraindo arquivos...")

    def _on_download_finished(self, extracted_dir: object) -> None:
        self.update_status_label.setText("Aplicando atualização e reiniciando...")
        if isinstance(extracted_dir, Path):
            self.update_restart_requested.emit(extracted_dir)
        else:
            self._on_update_failed("Diretório de arquivos extraídos inválido.")

    def _on_update_failed(self, err_msg: str) -> None:
        self.check_update_btn.setEnabled(True)
        self.apply_update_btn.setEnabled(True)
        self.update_progress_bar.setVisible(False)
        self.update_status_label.setText(f"Falha na atualização: {err_msg}")
        InfoBar.error("Erro na Atualização", err_msg, parent=self)
