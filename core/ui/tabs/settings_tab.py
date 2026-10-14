import threading
from pathlib import Path

import yaml
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import InfoBar, LineEdit

from core.infra.config import config, update_yaml_active_provider
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.infra.presets import detect_recommended_preset, get_system_hardware_info
from core.infra.update_preferences import UpdatePreferenceManager
from core.infra.updater import ReleaseInfo, UpdateManager
from core.shared.constants import DEFAULT_PROVIDER
from core.shared.paths import get_app_root, get_app_version


class SettingsTab(QWidget):
    """Tab widget for managing LLM providers, API keys, performance, and updates."""

    restart_requested = Signal()
    update_restart_requested = Signal(object)
    provider_changed = Signal(str)
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
        active = config.get("llm", {}).get("active_provider", DEFAULT_PROVIDER)
        if active in self.providers:
            self.provider_combo.setCurrentIndex(self.providers.index(active))
        form.addRow(QLabel("Provedor LLM:"), self.provider_combo)

        self.api_key_input = LineEdit(self)
        self.api_key_input.setPlaceholderText("Cole sua chave de API aqui...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(QLabel("Nova Chave:"), self.api_key_input)

        self.save_key_btn = QPushButton("Salvar Chave", self)
        self.save_key_btn.clicked.connect(self._save_key)
        form.addRow(self.save_key_btn)

        self.set_active_btn = QPushButton("Definir como Provedor Ativo", self)
        self.set_active_btn.clicked.connect(self._set_active_provider)
        form.addRow(self.set_active_btn)

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

        # Updates Group
        self.update_mgr = UpdateManager()
        self.pref_mgr = UpdatePreferenceManager()
        self._latest_release: ReleaseInfo | None = None

        self.update_checked.connect(self._on_update_check_finished)
        self.update_progress.connect(self._on_update_progress)
        self.update_extracting.connect(self._on_update_extracting)
        self.update_download_finished.connect(self._on_download_finished)
        self.update_failed.connect(self._on_update_failed)

        update_group = QGroupBox("Atualizações do Sistema", self)
        update_layout = QVBoxLayout(update_group)

        self.version_label = QLabel(
            f"<b>Versão Instalada:</b> v{get_app_version()}", self
        )
        update_layout.addWidget(self.version_label)

        self.update_status_label = QLabel(
            "Nenhuma verificação recente realizada.", self
        )
        self.update_status_label.setWordWrap(True)
        update_layout.addWidget(self.update_status_label)

        btn_row = QHBoxLayout()
        self.check_update_btn = QPushButton("Verificar Atualizações", self)
        self.check_update_btn.clicked.connect(self._on_check_update_clicked)
        btn_row.addWidget(self.check_update_btn)

        self.apply_update_btn = QPushButton("Baixar e Atualizar", self)
        self.apply_update_btn.setVisible(False)
        self.apply_update_btn.clicked.connect(self._download_and_apply_update)
        btn_row.addWidget(self.apply_update_btn)

        self.snooze_btn = QPushButton("Lembrar Mais Tarde", self)
        self.snooze_btn.setVisible(False)
        self.snooze_btn.clicked.connect(self._on_snooze_clicked)
        btn_row.addWidget(self.snooze_btn)

        update_layout.addLayout(btn_row)

        self.update_progress_bar = QProgressBar(self)
        self.update_progress_bar.setVisible(False)
        update_layout.addWidget(self.update_progress_bar)

        layout.addWidget(update_group)
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
            yaml_path = get_app_root() / "config.yaml"
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data["performance_profile"] = new_prof
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            InfoBar.success(
                "Configuração Salva", "Reiniciando o Jarvis...", parent=self
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
                from core.ai.llm_agent import llm_agent

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

        from core.ai.llm_agent import llm_agent

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
