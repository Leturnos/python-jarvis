import re
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
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
from core.audio.audio_engine import get_input_devices
from core.audio.voice_catalog import (
    DEFAULT_STAGE_PHRASES,
    DEFAULT_VOICE_ID,
    STAGE_PHRASE_PRESETS,
    VOICE_CATALOG,
    get_voice_preset,
)
from core.audio.voice_manager import VoiceManager
from core.infra.config import (
    config,
    update_yaml_active_provider,
    update_yaml_bool_setting,
    update_yaml_device_index,
    update_yaml_float_setting,
    update_yaml_int_setting,
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
from core.runtime.state import JarvisState, state_manager
from core.shared.constants import DEFAULT_PROVIDER
from core.shared.paths import get_app_version, get_user_config_path
from core.shared.utils import is_autostart_enabled_check, manage_autostart
from core.ui.screen_position import SCREEN_POSITION_LABELS, SCREEN_POSITIONS_ORDER
from core.ui.widgets.audio_calibration_dialog import AudioCalibrationDialog
from core.ui.widgets.hotkey_recorder import HotkeyRecorder
from core.ui.widgets.safe_slider import SafeSlider
from core.ui.widgets.voice_combo_box import TwoColumnVoiceComboBox


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
    voice_download_progress = Signal(int, int)
    voice_download_finished = Signal(str)
    voice_download_failed = Signal(str)

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

    def __init__(self, parent: QWidget | None = None, ui_adapter: Any = None) -> None:
        super().__init__(parent)

        self.ui_adapter = ui_adapter
        self.voice_mgr = VoiceManager()
        self._is_downloading_voice = False
        self._active_recorder: HotkeyRecorder | None = None
        self._active_field: str | None = None
        self._prev_recorded_val: str = ""

        self.voice_download_progress.connect(self._on_voice_download_progress)
        self.voice_download_finished.connect(self._on_voice_download_finished)
        self.voice_download_failed.connect(self._on_voice_download_failed)

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
        layout.setContentsMargins(0, 2, 8, 8)
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

        # Card 2.5: Microphone & Wake Word Sensitivity
        mic_card = SimpleCardWidget(scroll_content)
        self._style_card(mic_card)
        mic_layout = QVBoxLayout(mic_card)
        mic_layout.setContentsMargins(16, 12, 16, 12)
        mic_layout.setSpacing(10)

        mic_title = StrongBodyLabel("🎙️ Microfone & Sensibilidade de Ativação", mic_card)
        mic_layout.addWidget(mic_title)

        mic_desc = CaptionLabel(
            "Selecione o microfone, ajuste ganho e sensibilidade ou calibre pelo assistente.",
            mic_card,
        )
        mic_desc.setWordWrap(True)
        mic_desc.setStyleSheet("color: #82828e;")
        mic_layout.addWidget(mic_desc)

        # Row 1: Audio Input Device Selector
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        dev_lbl = BodyLabel("Dispositivo de Entrada:", mic_card)
        dev_lbl.setFixedWidth(165)
        dev_row.addWidget(dev_lbl)

        self.input_device_combo = ComboBox(mic_card)
        self.input_device_combo.setMinimumWidth(180)
        self.input_device_combo.setMaximumWidth(375)
        self.input_device_combo.addItem("Padrão do Sistema (Windows)", userData=None)

        try:
            input_devs = get_input_devices()
            cur_dev_idx = config.get("voice_activation", {}).get("device_index")
            selected_combo_idx = 0
            for idx, (d_idx, d_name) in enumerate(input_devs):
                self.input_device_combo.addItem(d_name, userData=d_idx)
                if cur_dev_idx is not None and int(cur_dev_idx) == d_idx:
                    selected_combo_idx = idx + 1
            self.input_device_combo.setCurrentIndex(selected_combo_idx)
        except Exception as e:
            logger.warning(f"Error listing input devices: {e}")

        dev_row.addWidget(self.input_device_combo, 1)
        mic_layout.addLayout(dev_row)

        # Row 2: Wake Word Threshold Slider
        th_row = QHBoxLayout()
        th_row.setSpacing(8)
        th_lbl = BodyLabel("Sensibilidade Wake Word:", mic_card)
        th_lbl.setFixedWidth(165)
        th_row.addWidget(th_lbl)

        cur_th = float(
            config.get("voice_activation", {})
            .get("wake_word", {})
            .get("threshold", config.get("jarvis", {}).get("threshold", 0.50))
        )
        self.wake_threshold_val_lbl = StrongBodyLabel(f"{cur_th:.2f}", mic_card)
        self.wake_threshold_val_lbl.setStyleSheet("color: #4cc2ff;")
        self.wake_threshold_val_lbl.setFixedWidth(40)
        self.wake_threshold_val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.wake_threshold_slider = SafeSlider(Qt.Orientation.Horizontal, mic_card)
        self.wake_threshold_slider.setRange(10, 90)
        self.wake_threshold_slider.setValue(int(cur_th * 100))
        self.wake_threshold_slider.valueChanged.connect(
            lambda v: self.wake_threshold_val_lbl.setText(f"{v / 100.0:.2f}")
        )
        th_row.addWidget(self.wake_threshold_slider, 1)
        th_row.addWidget(self.wake_threshold_val_lbl)
        mic_layout.addLayout(th_row)

        # Row 3: Microphone Volume Multiplier Slider
        gain_row = QHBoxLayout()
        gain_row.setSpacing(8)
        gain_lbl = BodyLabel("Ganho do Microfone:", mic_card)
        gain_lbl.setFixedWidth(165)
        gain_row.addWidget(gain_lbl)

        cur_gain = float(
            config.get("voice_activation", {}).get(
                "volume_multiplier",
                config.get("jarvis", {}).get("volume_multiplier", 1.0),
            )
        )
        self.mic_gain_val_lbl = StrongBodyLabel(f"{cur_gain:.1f}x", mic_card)
        self.mic_gain_val_lbl.setStyleSheet("color: #4cc2ff;")
        self.mic_gain_val_lbl.setFixedWidth(40)
        self.mic_gain_val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.mic_gain_slider = SafeSlider(Qt.Orientation.Horizontal, mic_card)
        self.mic_gain_slider.setRange(5, 25)
        self.mic_gain_slider.setValue(int(cur_gain * 10))
        self.mic_gain_slider.valueChanged.connect(
            lambda v: self.mic_gain_val_lbl.setText(f"{v / 10.0:.1f}x")
        )
        gain_row.addWidget(self.mic_gain_slider, 1)
        gain_row.addWidget(self.mic_gain_val_lbl)
        mic_layout.addLayout(gain_row)

        # Action Buttons Row
        mic_btns_row = QHBoxLayout()
        mic_btns_row.setSpacing(10)

        self.calibrate_mic_btn = PrimaryPushButton("🎙️ Calibrar Microfone...", mic_card)
        self.calibrate_mic_btn.clicked.connect(self._open_audio_calibration_dialog)
        mic_btns_row.addWidget(self.calibrate_mic_btn)

        mic_btns_row.addStretch(1)

        self.save_mic_btn = PushButton("Salvar Ajustes", mic_card)
        self.save_mic_btn.setFixedWidth(130)
        self.save_mic_btn.clicked.connect(self._save_audio_settings)
        mic_btns_row.addWidget(self.save_mic_btn)

        mic_layout.addLayout(mic_btns_row)
        layout.addWidget(mic_card)

        # Card 2.8: Assistant Voice & Downloadable Neural Voice Packs
        voice_card = SimpleCardWidget(scroll_content)
        self._style_card(voice_card)
        voice_layout = QVBoxLayout(voice_card)
        voice_layout.setContentsMargins(16, 12, 16, 12)
        voice_layout.setSpacing(10)

        voice_title = StrongBodyLabel(
            "🗣️ Voz do Assistente (Pacotes de Voz)", voice_card
        )
        voice_layout.addWidget(voice_title)

        voice_sub = CaptionLabel(
            "Escolha a voz do Jarvis (incluindo J.A.R.V.I.S. Mark III e F.R.I.D.A.Y.), ajuste velocidade/volume ou limpe pacotes não usados.",
            voice_card,
        )
        voice_sub.setWordWrap(True)
        voice_sub.setStyleSheet("color: #82828e;")
        voice_layout.addWidget(voice_sub)

        # Row 1: Voice Preset Selector (2-column aligned: Name | Model Weight)
        v_sel_row = QHBoxLayout()
        v_sel_row.setSpacing(8)
        v_sel_lbl = BodyLabel("Voz / Persona:", voice_card)
        v_sel_lbl.setFixedWidth(165)
        v_sel_row.addWidget(v_sel_lbl)

        self.voice_combo = TwoColumnVoiceComboBox(voice_card)
        self.voice_ids = [preset.voice_id for preset in VOICE_CATALOG]
        v_sel_row.addWidget(self.voice_combo, 1)
        voice_layout.addLayout(v_sel_row)

        self.voice_desc_label = CaptionLabel("", voice_card)
        self.voice_desc_label.setWordWrap(True)
        self.voice_desc_label.setStyleSheet("color: #9da3b4;")
        voice_layout.addWidget(self.voice_desc_label)

        # Row 2: Speech Rate Slider (-6 to +6)
        rate_row = QHBoxLayout()
        rate_row.setSpacing(8)
        rate_lbl = BodyLabel("Velocidade da Fala:", voice_card)
        rate_lbl.setFixedWidth(165)
        rate_row.addWidget(rate_lbl)

        cur_rate = int(config.get("tts", {}).get("rate", 2))
        cur_rate = max(-6, min(6, cur_rate))
        self.tts_rate_val_lbl = StrongBodyLabel(f"{cur_rate:+d}", voice_card)
        self.tts_rate_val_lbl.setStyleSheet("color: #4cc2ff;")
        self.tts_rate_val_lbl.setFixedWidth(40)
        self.tts_rate_val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.tts_rate_slider = SafeSlider(Qt.Orientation.Horizontal, voice_card)
        self.tts_rate_slider.setRange(-6, 6)
        self.tts_rate_slider.setValue(cur_rate)
        self.tts_rate_slider.valueChanged.connect(
            lambda v: self.tts_rate_val_lbl.setText(f"{int(v):+d}")
        )
        rate_row.addWidget(self.tts_rate_slider, 1)
        rate_row.addWidget(self.tts_rate_val_lbl)
        voice_layout.addLayout(rate_row)

        # Row 3: Speech Volume Slider (10 to 100)
        vol_row = QHBoxLayout()
        vol_row.setSpacing(8)
        vol_lbl = BodyLabel("Volume da Voz:", voice_card)
        vol_lbl.setFixedWidth(165)
        vol_row.addWidget(vol_lbl)

        cur_vol = int(config.get("tts", {}).get("volume", 100))
        cur_vol = max(10, min(100, cur_vol))
        self.tts_volume_val_lbl = StrongBodyLabel(f"{cur_vol}%", voice_card)
        self.tts_volume_val_lbl.setStyleSheet("color: #4cc2ff;")
        self.tts_volume_val_lbl.setFixedWidth(40)
        self.tts_volume_val_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.tts_volume_slider = SafeSlider(Qt.Orientation.Horizontal, voice_card)
        self.tts_volume_slider.setRange(10, 100)
        self.tts_volume_slider.setValue(cur_vol)
        self.tts_volume_slider.valueChanged.connect(
            lambda v: self.tts_volume_val_lbl.setText(f"{int(v)}%")
        )
        vol_row.addWidget(self.tts_volume_slider, 1)
        vol_row.addWidget(self.tts_volume_val_lbl)
        voice_layout.addLayout(vol_row)

        # Progress bar for voice downloads (hidden by default)
        self.voice_dl_progress = ProgressBar(voice_card)
        self.voice_dl_progress.setRange(0, 100)
        self.voice_dl_progress.setValue(0)
        self.voice_dl_progress.setVisible(False)
        voice_layout.addWidget(self.voice_dl_progress)

        self.voice_dl_status_lbl = CaptionLabel("", voice_card)
        self.voice_dl_status_lbl.setWordWrap(True)
        self.voice_dl_status_lbl.setStyleSheet("color: #4cc2ff;")
        self.voice_dl_status_lbl.setVisible(False)
        voice_layout.addWidget(self.voice_dl_status_lbl)

        # Action Buttons Row
        v_btns_row = QHBoxLayout()
        v_btns_row.setSpacing(8)

        self.voice_action_btn = PrimaryPushButton("Definir como Voz Ativa", voice_card)
        self.voice_action_btn.clicked.connect(self._on_voice_primary_action)
        v_btns_row.addWidget(self.voice_action_btn)

        self.voice_preview_btn = PushButton("🔊 Ouvir Amostra", voice_card)
        self.voice_preview_btn.clicked.connect(self._on_preview_selected_voice)
        v_btns_row.addWidget(self.voice_preview_btn)

        v_btns_row.addStretch(1)

        self.cleanup_voices_btn = PushButton("🧹 Enxugar Vozes Não Usadas", voice_card)
        self.cleanup_voices_btn.setToolTip(
            "Apaga pacotes de voz baixados que não estão em uso (preserva a voz ativa e a voz nativa do Windows)."
        )
        self.cleanup_voices_btn.clicked.connect(self._on_cleanup_unused_voices)
        v_btns_row.addWidget(self.cleanup_voices_btn)

        voice_layout.addLayout(v_btns_row)
        layout.addWidget(voice_card)

        self._refresh_voice_selector_ui()
        self.voice_combo.currentIndexChanged.connect(self._on_voice_selection_changed)

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
        layout.setContentsMargins(0, 2, 8, 8)
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

        # Quick Phrase Kit presets row
        kit_row = QHBoxLayout()
        kit_row.setSpacing(6)
        kit_lbl = BodyLabel("Kits de Frases:", ai_card)
        kit_lbl.setFixedWidth(155)
        kit_row.addWidget(kit_lbl)

        self.phrase_kit_buttons: dict[str, PushButton] = {}
        for kit_name in STAGE_PHRASE_PRESETS:
            kit_btn = PushButton(kit_name, ai_card)
            kit_btn.setToolTip(f"Preencher frases das etapas com o estilo '{kit_name}'")
            kit_btn.clicked.connect(
                lambda checked=False, k=kit_name: self._apply_phrase_kit(k)
            )
            self.phrase_kit_buttons[kit_name] = kit_btn
            kit_row.addWidget(kit_btn)
        kit_row.addStretch(1)
        ai_layout.addLayout(kit_row)

        va_cfg = config.get("voice_activation", {})

        # Stage 1: Response Phrase (Wake Word / Activation)
        resp_row = QHBoxLayout()
        resp_row.setSpacing(8)
        resp_lbl = BodyLabel("Ao Ativar (Wake Word):", ai_card)
        resp_lbl.setFixedWidth(155)
        resp_row.addWidget(resp_lbl)

        self.response_phrase_input = FluentLineEdit(ai_card)
        cur_phrase = va_cfg.get(
            "response_phrase", DEFAULT_STAGE_PHRASES["response_phrase"]
        )
        self.response_phrase_input.setText(str(cur_phrase))
        self.response_phrase_input.setPlaceholderText(
            "Ex: Sim?, Às suas ordens, senhor."
        )
        self.response_phrase_input.setClearButtonEnabled(True)
        resp_row.addWidget(self.response_phrase_input, 1)

        self.preview_resp_btn = PushButton("🔊", ai_card)
        self.preview_resp_btn.setFixedWidth(40)
        self.preview_resp_btn.setToolTip("Ouvir frase de ativação")
        self.preview_resp_btn.clicked.connect(
            lambda: self._speak_sample_text(self.response_phrase_input.text())
        )
        resp_row.addWidget(self.preview_resp_btn)
        ai_layout.addLayout(resp_row)

        # Stage 2: Completion Phrase (When a task finishes)
        comp_row = QHBoxLayout()
        comp_row.setSpacing(8)
        comp_lbl = BodyLabel("Ao Concluir Tarefa:", ai_card)
        comp_lbl.setFixedWidth(155)
        comp_row.addWidget(comp_lbl)

        self.completion_phrase_input = FluentLineEdit(ai_card)
        cur_comp = va_cfg.get(
            "completion_phrase", DEFAULT_STAGE_PHRASES["completion_phrase"]
        )
        self.completion_phrase_input.setText(str(cur_comp))
        self.completion_phrase_input.setPlaceholderText(
            "Ex: Pronto!, Concluído, senhor."
        )
        self.completion_phrase_input.setClearButtonEnabled(True)
        comp_row.addWidget(self.completion_phrase_input, 1)

        self.preview_comp_btn = PushButton("🔊", ai_card)
        self.preview_comp_btn.setFixedWidth(40)
        self.preview_comp_btn.setToolTip("Ouvir frase de conclusão")
        self.preview_comp_btn.clicked.connect(
            lambda: self._speak_sample_text(self.completion_phrase_input.text())
        )
        comp_row.addWidget(self.preview_comp_btn)
        ai_layout.addLayout(comp_row)

        # Stage 3: No Speech Phrase (Silence detected)
        ns_row = QHBoxLayout()
        ns_row.setSpacing(8)
        ns_lbl = BodyLabel("Quando Não Ouvir:", ai_card)
        ns_lbl.setFixedWidth(155)
        ns_row.addWidget(ns_lbl)

        self.no_speech_phrase_input = FluentLineEdit(ai_card)
        cur_ns = va_cfg.get(
            "no_speech_phrase", DEFAULT_STAGE_PHRASES["no_speech_phrase"]
        )
        self.no_speech_phrase_input.setText(str(cur_ns))
        self.no_speech_phrase_input.setPlaceholderText("Ex: Desculpe, não ouvi nada.")
        self.no_speech_phrase_input.setClearButtonEnabled(True)
        ns_row.addWidget(self.no_speech_phrase_input, 1)

        self.preview_ns_btn = PushButton("🔊", ai_card)
        self.preview_ns_btn.setFixedWidth(40)
        self.preview_ns_btn.setToolTip("Ouvir frase de silêncio")
        self.preview_ns_btn.clicked.connect(
            lambda: self._speak_sample_text(self.no_speech_phrase_input.text())
        )
        ns_row.addWidget(self.preview_ns_btn)
        ai_layout.addLayout(ns_row)

        # Stage 4: Not Understood Phrase (STT empty / unrecognized)
        nu_row = QHBoxLayout()
        nu_row.setSpacing(8)
        nu_lbl = BodyLabel("Quando Não Entender:", ai_card)
        nu_lbl.setFixedWidth(155)
        nu_row.addWidget(nu_lbl)

        self.not_understood_phrase_input = FluentLineEdit(ai_card)
        cur_nu = va_cfg.get(
            "not_understood_phrase", DEFAULT_STAGE_PHRASES["not_understood_phrase"]
        )
        self.not_understood_phrase_input.setText(str(cur_nu))
        self.not_understood_phrase_input.setPlaceholderText(
            "Ex: Desculpe, não entendi., Poderia repetir, senhor?"
        )
        self.not_understood_phrase_input.setClearButtonEnabled(True)
        nu_row.addWidget(self.not_understood_phrase_input, 1)

        self.preview_nu_btn = PushButton("🔊", ai_card)
        self.preview_nu_btn.setFixedWidth(40)
        self.preview_nu_btn.setToolTip("Ouvir frase de não compreendido")
        self.preview_nu_btn.clicked.connect(
            lambda: self._speak_sample_text(self.not_understood_phrase_input.text())
        )
        nu_row.addWidget(self.preview_nu_btn)
        ai_layout.addLayout(nu_row)

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

        # Markdown / Obsidian notes folder row
        notes_row = QHBoxLayout()
        notes_row.setSpacing(8)
        notes_lbl = BodyLabel("Notas (Cofre Obsidian):", ai_card)
        notes_lbl.setFixedWidth(155)
        notes_row.addWidget(notes_lbl)

        self.notes_dir_input = FluentLineEdit(ai_card)
        self.notes_dir_input.setPlaceholderText("Caminho da pasta ou cofre (Opcional)")
        self.notes_dir_input.setClearButtonEnabled(True)
        cur_notes_dir = config.get("tools", {}).get("notes", {}).get("markdown_dir", "")
        self.notes_dir_input.setText(str(cur_notes_dir))
        notes_row.addWidget(self.notes_dir_input, 1)
        ai_layout.addLayout(notes_row)

        # Calendar ICS link row
        cal_row = QHBoxLayout()
        cal_row.setSpacing(8)
        cal_lbl = BodyLabel("Agenda (Link .ics):", ai_card)
        cal_lbl.setFixedWidth(155)
        cal_row.addWidget(cal_lbl)

        self.calendar_url_input = FluentLineEdit(ai_card)
        self.calendar_url_input.setPlaceholderText(
            "URL privada .ics (Google/Outlook, Opcional)"
        )
        self.calendar_url_input.setClearButtonEnabled(True)
        cur_cal = config.get("tools", {}).get("calendar", {}).get("ics_url", "")
        self.calendar_url_input.setText(str(cur_cal))
        cal_row.addWidget(self.calendar_url_input, 1)
        ai_layout.addLayout(cal_row)

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
        layout.setContentsMargins(0, 2, 8, 8)
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

        self.update_card = SimpleCardWidget(scroll_content)
        update_card = self.update_card
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

    def _open_audio_calibration_dialog(self) -> None:
        current_state = state_manager.get_state()
        if current_state in (
            JarvisState.LISTENING,
            JarvisState.THINKING,
            JarvisState.EXECUTING,
            JarvisState.CONFIRMING_DRY_RUN,
        ):
            InfoBar.warning(
                "Jarvis Ocupado",
                "Aguarde a conclusão do comando atual para calibrar o microfone.",
                parent=self.window(),
                duration=3500,
            )
            return
        """Opens the interactive 3-step audio and wake word calibration dialog."""
        dialog = AudioCalibrationDialog(
            ui_adapter=self.ui_adapter,
            on_apply=self._on_calibration_applied,
            parent=self.window(),
        )
        dialog.exec()

    def _on_calibration_applied(
        self, threshold: float, volume_multiplier: float, speech_rms: float
    ) -> None:
        """Callback invoked when calibration wizard completes and applies settings."""
        self.wake_threshold_slider.setValue(int(threshold * 100))
        self.mic_gain_slider.setValue(int(volume_multiplier * 10))
        if self.ui_adapter is not None and hasattr(
            self.ui_adapter, "apply_calibration"
        ):
            self.ui_adapter.apply_calibration(threshold, volume_multiplier, speech_rms)
        InfoBar.success(
            "Calibração Concluída!",
            f"Sensibilidade definida para {threshold:.2f} e ganho para {volume_multiplier:.1f}x.",
            parent=self.window(),
            duration=3500,
        )

    def _save_audio_settings(self) -> None:
        """Saves manual microphone and wake word threshold settings."""
        dev_data = self.input_device_combo.currentData()
        th_val = self.wake_threshold_slider.value() / 100.0
        gain_val = self.mic_gain_slider.value() / 10.0

        try:
            update_yaml_device_index(dev_data)
            update_yaml_float_setting(
                "voice_activation",
                "threshold",
                th_val,
                subsection="wake_word",
                precision=2,
            )
            update_yaml_float_setting(
                "voice_activation",
                "volume_multiplier",
                gain_val,
                precision=2,
            )
            if self.ui_adapter is not None and hasattr(
                self.ui_adapter, "apply_calibration"
            ):
                self.ui_adapter.apply_calibration(th_val, gain_val)

            dev_name = "Padrão" if dev_data is None else f"ID {dev_data}"
            dev_suffix = " (ativo ao reiniciar)" if dev_data is not None else ""
            InfoBar.success(
                "Ajustes de Áudio Salvos!",
                f"Dispositivo: {dev_name}{dev_suffix} | Sensibilidade: {th_val:.2f} | Ganho: {gain_val:.1f}x.",
                parent=self.window(),
                duration=3500,
            )
        except Exception as e:
            logger.error(f"Error saving audio settings: {e}")
            InfoBar.error("Erro ao Salvar", str(e), parent=self.window(), duration=3500)

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
        phrase = (
            self.response_phrase_input.text().strip()
            or DEFAULT_STAGE_PHRASES["response_phrase"]
        )
        comp_phrase = (
            self.completion_phrase_input.text().strip()
            or DEFAULT_STAGE_PHRASES["completion_phrase"]
        )
        ns_phrase = (
            self.no_speech_phrase_input.text().strip()
            or DEFAULT_STAGE_PHRASES["no_speech_phrase"]
        )
        nu_phrase = (
            self.not_understood_phrase_input.text().strip()
            or DEFAULT_STAGE_PHRASES["not_understood_phrase"]
        )
        ws_prov = self.web_search_options[self.web_search_combo.currentIndex()]
        city = self.city_input.text().strip() or "São Paulo"
        notes_dir = self.notes_dir_input.text().strip()
        cal_url = self.calendar_url_input.text().strip()

        config.setdefault("tools", {}).setdefault("notes", {})["markdown_dir"] = (
            notes_dir
        )
        config.setdefault("tools", {}).setdefault("calendar", {})["ics_url"] = cal_url

        config.setdefault("ai", {})["proactivity"] = proact
        va_dict = config.setdefault("voice_activation", {})
        va_dict["response_phrase"] = phrase
        va_dict["completion_phrase"] = comp_phrase
        va_dict["no_speech_phrase"] = ns_phrase
        va_dict["not_understood_phrase"] = nu_phrase
        config.setdefault("tools", {}).setdefault("web_search", {})["provider"] = (
            ws_prov
        )
        config.setdefault("tools", {}).setdefault("weather", {})["default_city"] = city

        try:
            update_yaml_str_setting("ai", "proactivity", proact)
            update_yaml_str_setting("voice_activation", "response_phrase", phrase)
            update_yaml_str_setting(
                "voice_activation", "completion_phrase", comp_phrase
            )
            update_yaml_str_setting("voice_activation", "no_speech_phrase", ns_phrase)
            update_yaml_str_setting(
                "voice_activation", "not_understood_phrase", nu_phrase
            )
            update_yaml_str_setting(
                "tools", "provider", ws_prov, subsection="web_search"
            )
            update_yaml_weather_city(city)
            update_yaml_str_setting(
                "tools", "markdown_dir", notes_dir, subsection="notes"
            )
            update_yaml_str_setting("tools", "ics_url", cal_url, subsection="calendar")
        except Exception as e:
            logger.warning(f"Could not persist AI preferences to yaml: {e}")

        InfoBar.success(
            title="Preferências Salvas",
            content=f"Configurações de IA e frases salvas com sucesso (Cidade: '{city}', Proatividade: '{proact}').",
            parent=self.window(),
            duration=3000,
        )
        logger.info(
            f"Saved AI preferences: proactivity='{proact}', phrase='{phrase}', completion='{comp_phrase}', web_search='{ws_prov}', city='{city}'."
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

    def focus_update_section(self) -> None:
        """Switches to the System sub-tab, scrolls to the bottom, and pulses the update section."""
        self.sub_pivot.setCurrentItem("sys_upd")
        self.sub_stack.setCurrentWidget(self.pane_sys_upd)
        self._scroll_to_update_card()
        QTimer.singleShot(80, self._scroll_to_update_card)
        QTimer.singleShot(120, self._start_update_pulse)

    def _scroll_to_update_card(self) -> None:
        """Scrolls the System sub-tab scroll area all the way down to the update card."""
        if hasattr(self, "sys_scroll") and self.sys_scroll is not None:
            if hasattr(self, "update_card") and self.update_card is not None:
                self.sys_scroll.ensureWidgetVisible(self.update_card, 0, 24)
            vbar = self.sys_scroll.verticalScrollBar()
            if vbar is not None:
                vbar.setValue(vbar.maximum())

    def _start_update_pulse(self) -> None:
        """Pulses the update card and action buttons to draw visual attention."""
        pulse_timer = getattr(self, "_update_pulse_timer", None)
        if pulse_timer is not None:
            try:
                pulse_timer.stop()
            except Exception:
                pass

        self._pulse_step = 0
        timer = QTimer(self)
        self._update_pulse_timer = timer

        def _tick() -> None:
            self._pulse_step += 1
            if self._pulse_step > 6:
                timer.stop()
                if hasattr(self, "update_card"):
                    self._style_card(self.update_card)
                self.check_update_btn.setStyleSheet("")
                return

            is_highlight = self._pulse_step % 2 == 1
            if hasattr(self, "update_card"):
                if is_highlight:
                    self.update_card.setStyleSheet(
                        """
                        SimpleCardWidget {
                            background-color: #1e2631;
                            border: 1.5px solid #4cc2ff;
                            border-radius: 9px;
                        }
                        """
                    )
                else:
                    self._style_card(self.update_card)

            if is_highlight:
                self.check_update_btn.setStyleSheet(
                    "PushButton { border: 1.5px solid #4cc2ff; color: #4cc2ff; font-weight: 600; }"
                )
            else:
                self.check_update_btn.setStyleSheet("")

        timer.timeout.connect(_tick)
        _tick()
        timer.start(240)

    # ------------------------------------------------------------------
    # Assistant Voice Catalog, Download, Preview & Cleanup Handlers
    # ------------------------------------------------------------------
    def _get_tts_engine(self) -> Any:
        """Returns the live TTSEngine from ui_adapter.controller if available."""
        ctrl = getattr(self.ui_adapter, "controller", None)
        if ctrl is not None:
            return getattr(ctrl, "tts_engine", None)
        return None

    def _refresh_voice_selector_ui(self, select_voice_id: str | None = None) -> None:
        """Populates the voice combo box with installation badges and updates button states."""
        active_voice_id = str(
            config.get("tts", {}).get("active_voice_id", DEFAULT_VOICE_ID)
        )
        target_voice_id = select_voice_id or (
            self.voice_ids[self.voice_combo.currentIndex()]
            if self.voice_combo.count() == len(self.voice_ids)
            and 0 <= self.voice_combo.currentIndex() < len(self.voice_ids)
            else active_voice_id
        )

        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for preset in VOICE_CATALOG:
            if preset.provider == "sapi5" or preset.model_asset is None:
                badge = "0 MB · Nativa"
            elif self.voice_mgr.is_voice_installed(preset.voice_id):
                badge = f"✓ {preset.model_asset.approx_size_mb:.1f} MB"
            else:
                badge = f"⬇ {preset.model_asset.approx_size_mb:.1f} MB"

            active_prefix = "★ " if preset.voice_id == active_voice_id else ""
            self.voice_combo.addItem(f"{active_prefix}{preset.display_name}\t{badge}")

        if target_voice_id in self.voice_ids:
            self.voice_combo.setCurrentIndex(self.voice_ids.index(target_voice_id))
        else:
            self.voice_combo.setCurrentIndex(0)
        self.voice_combo.blockSignals(False)

        self._update_voice_action_controls()

    def _on_voice_selection_changed(self, _index: int) -> None:
        if not self._is_downloading_voice:
            self.voice_dl_status_lbl.setVisible(False)
        self._update_voice_action_controls()

    def _update_voice_action_controls(self) -> None:
        idx = self.voice_combo.currentIndex()
        if idx < 0 or idx >= len(self.voice_ids):
            return

        selected_id = self.voice_ids[idx]
        preset = get_voice_preset(selected_id)
        active_id = str(config.get("tts", {}).get("active_voice_id", DEFAULT_VOICE_ID))
        installed = self.voice_mgr.is_voice_installed(selected_id)

        self.voice_desc_label.setText(preset.description)

        if self._is_downloading_voice:
            self.voice_action_btn.setEnabled(False)
            self.voice_preview_btn.setEnabled(False)
            self.cleanup_voices_btn.setEnabled(False)
            return

        self.voice_action_btn.setEnabled(True)
        self.voice_preview_btn.setEnabled(installed)
        if installed:
            self.voice_preview_btn.setToolTip(
                "Ouvir amostra real desta voz com a velocidade e volume atuais."
            )
        else:
            self.voice_preview_btn.setToolTip(
                "Baixe o pacote desta voz primeiro para ouvir a amostra (você pode enxugar/apagar depois se não usar)."
            )

        if installed:
            if selected_id == active_id:
                self.voice_action_btn.setText("Salvar Ajustes")
            else:
                self.voice_action_btn.setText("Definir como Ativa")
        else:
            mb = preset.model_asset.approx_size_mb if preset.model_asset else 60.0
            self.voice_action_btn.setText(f"⬇️ Baixar e Ativar ({mb:.0f} MB)")

        unused_count, unused_bytes = self.voice_mgr.get_unused_downloaded_stats(
            active_id
        )
        if unused_count > 0:
            unused_mb = unused_bytes / (1024 * 1024)
            self.cleanup_voices_btn.setText(
                f"🧹 Enxugar ({unused_count} · {unused_mb:.0f} MB)"
            )
            self.cleanup_voices_btn.setEnabled(True)
        else:
            self.cleanup_voices_btn.setText("🧹 Enxugar Não Usadas")
            self.cleanup_voices_btn.setEnabled(False)

    def _save_active_voice_and_sliders(self, voice_id: str) -> None:
        """Persists active_voice_id, rate, and volume to config and config.yaml."""
        rate_val = int(self.tts_rate_slider.value())
        vol_val = int(self.tts_volume_slider.value())
        preset = get_voice_preset(voice_id)

        tts_cfg = config.setdefault("tts", {})
        tts_cfg["active_voice_id"] = preset.voice_id
        tts_cfg["rate"] = rate_val
        tts_cfg["volume"] = vol_val

        try:
            update_yaml_str_setting("tts", "active_voice_id", preset.voice_id)
            update_yaml_int_setting("tts", "rate", rate_val)
            update_yaml_int_setting("tts", "volume", vol_val)
        except Exception as e:
            logger.warning(f"Could not persist TTS settings to yaml: {e}")

        self._refresh_voice_selector_ui(select_voice_id=preset.voice_id)
        InfoBar.success(
            title="Voz Atualizada!",
            content=f"Voz ativa: {preset.display_name} (Velocidade: {rate_val:+d}, Volume: {vol_val}%).",
            parent=self.window(),
            duration=3500,
        )

    def _on_voice_primary_action(self) -> None:
        idx = self.voice_combo.currentIndex()
        if idx < 0 or idx >= len(self.voice_ids):
            return

        selected_id = self.voice_ids[idx]
        if self.voice_mgr.is_voice_installed(selected_id):
            self._save_active_voice_and_sliders(selected_id)
            return

        # Trigger secure background download
        preset = get_voice_preset(selected_id)
        self._is_downloading_voice = True
        self.voice_dl_progress.setValue(0)
        self.voice_dl_progress.setVisible(True)
        self.voice_dl_status_lbl.setStyleSheet("color: #4cc2ff;")
        self.voice_dl_status_lbl.setText(
            f"Baixando pacote seguro para '{preset.display_name}'..."
        )
        self.voice_dl_status_lbl.setVisible(True)
        self._update_voice_action_controls()

        def _dl_worker() -> None:
            try:

                def _prog(down: int, total: int) -> None:
                    if total > 0:
                        self.voice_download_progress.emit(down, total)

                self.voice_mgr.download_voice_model(
                    selected_id, progress_callback=_prog
                )
                self.voice_download_finished.emit(selected_id)
            except Exception as exc:
                logger.error(f"Voice download failed for '{selected_id}': {exc}")
                friendly_msg = self.voice_mgr.format_user_error(exc)
                self.voice_download_failed.emit(friendly_msg)

        threading.Thread(target=_dl_worker, daemon=True).start()

    def _on_voice_download_progress(self, downloaded: int, total: int) -> None:
        pct = int((downloaded / total) * 100) if total > 0 else 0
        self.voice_dl_progress.setValue(pct)
        mb_down = downloaded / (1024 * 1024)
        mb_total = total / (1024 * 1024)
        self.voice_dl_status_lbl.setText(
            f"Baixando e verificando integridade: {mb_down:.1f} MB / {mb_total:.1f} MB ({pct}%)"
        )

    def _on_voice_download_finished(self, voice_id: str) -> None:
        self._is_downloading_voice = False
        self.voice_dl_progress.setVisible(False)
        self.voice_dl_status_lbl.setVisible(False)
        self._save_active_voice_and_sliders(voice_id)
        preset = get_voice_preset(voice_id)
        self._speak_sample_text(preset.sample_text, voice_id=voice_id)

    def _on_voice_download_failed(self, err_msg: str) -> None:
        self._is_downloading_voice = False
        self.voice_dl_progress.setVisible(False)
        friendly = self.voice_mgr.format_user_error(err_msg)
        self.voice_dl_status_lbl.setStyleSheet("color: #ff7b72;")
        self.voice_dl_status_lbl.setText(f"⚠️ {friendly}")
        self.voice_dl_status_lbl.setVisible(True)
        self._update_voice_action_controls()
        InfoBar.error(
            title="Não foi possível baixar a voz",
            content=friendly,
            parent=self.window(),
            duration=5000,
        )

    def _on_preview_selected_voice(self) -> None:
        idx = self.voice_combo.currentIndex()
        if idx < 0 or idx >= len(self.voice_ids):
            return
        selected_id = self.voice_ids[idx]
        if not self.voice_mgr.is_voice_installed(selected_id):
            return
        preset = get_voice_preset(selected_id)

        # Apply current slider values in memory before speaking sample
        tts_cfg = config.setdefault("tts", {})
        tts_cfg["rate"] = int(self.tts_rate_slider.value())
        tts_cfg["volume"] = int(self.tts_volume_slider.value())
        self._speak_sample_text(preset.sample_text, voice_id=selected_id)

    def _speak_sample_text(self, text: str, voice_id: str | None = None) -> None:
        clean = text.strip()
        if not clean:
            return
        tts_engine = self._get_tts_engine()
        if tts_engine is not None and hasattr(tts_engine, "speak_preview"):
            tts_engine.speak_preview(clean, voice_id=voice_id)
        else:
            InfoBar.info(
                "Amostra de Voz",
                f'"{clean}"',
                parent=self.window(),
                duration=2500,
            )

    def _on_cleanup_unused_voices(self) -> None:
        active_id = str(config.get("tts", {}).get("active_voice_id", DEFAULT_VOICE_ID))
        tts_engine = self._get_tts_engine()
        if tts_engine is not None and hasattr(tts_engine, "evict_cached_models"):
            tts_engine.evict_cached_models()

        removed_count, freed_bytes = self.voice_mgr.cleanup_unused_voices(active_id)
        self._refresh_voice_selector_ui()

        if removed_count > 0:
            freed_mb = freed_bytes / (1024 * 1024)
            InfoBar.success(
                title="Limpeza Concluída!",
                content=f"{removed_count} pacote(s) não usado(s) removido(s) ({freed_mb:.1f} MB liberados).",
                parent=self.window(),
                duration=4000,
            )
        else:
            InfoBar.info(
                title="Nada para Limpar",
                content="Nenhum pacote de voz não utilizado foi encontrado em disco.",
                parent=self.window(),
                duration=3000,
            )

    def _apply_phrase_kit(self, kit_name: str) -> None:
        """Fills the 4 stage phrase inputs with a thematic preset kit."""
        kit = STAGE_PHRASE_PRESETS.get(kit_name)
        if not kit:
            return
        self.response_phrase_input.setText(kit["response_phrase"])
        self.completion_phrase_input.setText(kit["completion_phrase"])
        self.no_speech_phrase_input.setText(kit["no_speech_phrase"])
        self.not_understood_phrase_input.setText(kit["not_understood_phrase"])
        InfoBar.info(
            title=f"Kit '{kit_name}' Aplicado",
            content="Clique em 'Salvar Preferências da IA' para gravar as frases.",
            parent=self.window(),
            duration=2800,
        )
