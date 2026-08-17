import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import InfoBar

from core.infra.config import config
from core.infra.keyring_manager import KeyringManager
from core.infra.presets import detect_recommended_preset, get_system_hardware_info


class SettingsTab(QWidget):
    """Tab widget for managing LLM providers, API keys, and performance settings."""

    restart_requested = Signal()

    PROFILES_ORDER = [
        "auto",
        "ultra_economic",
        "economic",
        "balanced",
        "performance",
    ]
    PROFILE_LABELS = {
        "auto": "Auto (Automático)",
        "ultra_economic": "Ultra Econômico (PC Muito Fraco)",
        "economic": "Econômico (PC Entrada)",
        "balanced": "Equilibrado (Recomendado)",
        "performance": "Alto Desempenho (PC Gamer/Workstation)",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Provider Group
        provider_group = QGroupBox("Provedor LLM", self)
        form = QFormLayout(provider_group)
        self.provider_combo = QComboBox(self)
        self.providers = [
            "gemini",
            "openai",
            "anthropic",
            "deepseek",
            "openrouter",
        ]
        self.provider_combo.addItems([p.capitalize() for p in self.providers])
        active = config.get("llm", {}).get("active_provider", "gemini")
        if active in self.providers:
            self.provider_combo.setCurrentIndex(self.providers.index(active))
        form.addRow(QLabel("Provedor LLM Ativo:"), self.provider_combo)

        self.check_key_btn = QPushButton("Validar Chave do Provedor", self)
        self.check_key_btn.clicked.connect(self._validate_key)
        form.addRow(self.check_key_btn)
        layout.addWidget(provider_group)

        # Performance Profile Group
        perf_group = QGroupBox("Perfil de Desempenho do Sistema", self)
        perf_layout = QVBoxLayout(perf_group)

        self.slider_label = QLabel(self)
        perf_layout.addWidget(self.slider_label)

        self.slider = QSlider(Qt.Orientation.Horizontal, self)
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

        self.desc_label = QLabel(self)
        self.desc_label.setWordWrap(True)
        perf_layout.addWidget(self.desc_label)

        self.apply_btn = QPushButton("Aplicar e Reiniciar Jarvis", self)
        self.apply_btn.setVisible(False)
        self.apply_btn.clicked.connect(self._apply_and_restart)
        perf_layout.addWidget(self.apply_btn)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self._update_slider_text(self.slider.value())

        layout.addWidget(perf_group)
        layout.addStretch(1)

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
            with open("config.yaml", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["performance_profile"] = new_prof
            with open("config.yaml", "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            InfoBar.success(
                "Configuração Salva", "Reiniciando o Jarvis...", parent=self
            )
            self.restart_requested.emit()
        except Exception as e:
            InfoBar.error("Erro", f"Falha ao salvar configuração: {e}", parent=self)

    def _validate_key(self) -> None:
        idx = self.provider_combo.currentIndex()
        prov = self.providers[idx]
        has_key = KeyringManager.validate_provider_key(prov)
        if has_key:
            InfoBar.success(
                "API Key Status",
                f"Key for {prov.capitalize()} is configured.",
                parent=self,
            )
        else:
            InfoBar.warning(
                "API Key Status",
                f"Key for {prov.capitalize()} is missing.",
                parent=self,
            )
