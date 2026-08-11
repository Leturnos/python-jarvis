from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import InfoBar

from core.infra.config import config
from core.infra.keyring_manager import KeyringManager


class SettingsTab(QWidget):
    """Tab widget for managing LLM providers, API keys, and voice settings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.provider_combo = QComboBox(self)
        self.providers = ["gemini", "openai", "anthropic", "deepseek", "openrouter"]
        self.provider_combo.addItems([p.capitalize() for p in self.providers])
        active = config.get("llm", {}).get("active_provider", "gemini")
        if active in self.providers:
            self.provider_combo.setCurrentIndex(self.providers.index(active))
        form.addRow(QLabel("Active LLM Provider:"), self.provider_combo)

        self.check_key_btn = QPushButton("Validate Provider Key", self)
        self.check_key_btn.clicked.connect(self._validate_key)
        form.addRow(self.check_key_btn)

        layout.addLayout(form)
        layout.addStretch(1)

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
