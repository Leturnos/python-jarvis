import threading
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSlider,
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
    SimpleCardWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
)
from qfluentwidgets import (
    LineEdit as FluentLineEdit,
)

from core.infra.config import (
    config,
    update_yaml_active_provider,
    update_yaml_performance_profile,
    update_yaml_weather_city,
)
from core.infra.keyring_manager import KeyringManager
from core.infra.logger_config import logger
from core.infra.presets import detect_recommended_preset, get_system_hardware_info
from core.infra.update_preferences import UpdatePreferenceManager
from core.infra.updater import ReleaseInfo, UpdateManager
from core.shared.constants import DEFAULT_PROVIDER
from core.shared.paths import get_app_version, get_user_config_path


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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # Header Row: Title, Subtitle, and Direct Config File/Folder Openers
        # ----------------------------------------------------------------------
        header_widget = QWidget(self)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = SubtitleLabel("Configurações do Sistema", self)
        title_box.addWidget(self.title_label)

        self.subtitle_label = CaptionLabel(
            "Gerencie provedores de IA, chaves, perfil de hardware, localização e atualizações.",
            self,
        )
        self.subtitle_label.setWordWrap(True)
        title_box.addWidget(self.subtitle_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch(1)

        self.open_config_btn = TransparentToolButton(FluentIcon.DOCUMENT, self)
        self.open_config_btn.setToolTip("Abrir config.yaml no editor padrão")
        self.open_config_btn.clicked.connect(self._open_config_file)
        header_layout.addWidget(self.open_config_btn)

        self.open_folder_btn = TransparentToolButton(FluentIcon.FOLDER, self)
        self.open_folder_btn.setToolTip(
            "Abrir pasta de configuração no Windows Explorer"
        )
        self.open_folder_btn.clicked.connect(self._open_config_folder)
        header_layout.addWidget(self.open_folder_btn)

        main_layout.addWidget(header_widget)

        # ----------------------------------------------------------------------
        # Smooth Scroll Area for Settings Cards
        # ----------------------------------------------------------------------
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 8, 0)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ----------------------------------------------------------------------
        # Card 1: AI / LLM Provider & Key Management
        # ----------------------------------------------------------------------
        provider_card = SimpleCardWidget(self.cards_container)
        provider_layout = QVBoxLayout(provider_card)
        provider_layout.setContentsMargins(16, 14, 16, 14)
        provider_layout.setSpacing(10)

        provider_title = StrongBodyLabel(
            "Provedor de Inteligência Artificial", provider_card
        )
        provider_layout.addWidget(provider_title)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        prov_lbl = BodyLabel("Provedor:", provider_card)
        prov_lbl.setFixedWidth(75)
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
        self.provider_combo.setMinimumWidth(150)
        self.provider_combo.setMaximumWidth(200)
        row1.addWidget(self.provider_combo)

        self.set_active_btn = PrimaryPushButton(
            "Definir como Provedor Ativo", provider_card
        )
        self.set_active_btn.clicked.connect(self._set_active_provider)
        row1.addWidget(self.set_active_btn)
        row1.addStretch(1)
        provider_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        key_lbl = BodyLabel("Nova Chave:", provider_card)
        key_lbl.setFixedWidth(75)
        row2.addWidget(key_lbl)

        self.api_key_input = PasswordLineEdit(provider_card)
        self.api_key_input.setPlaceholderText("Cole sua chave de API aqui...")
        self.api_key_input.setClearButtonEnabled(True)
        row2.addWidget(self.api_key_input, 1)
        provider_layout.addLayout(row2)

        key_btn_row = QHBoxLayout()
        key_btn_row.setSpacing(10)
        key_btn_row.addSpacing(85)

        self.save_key_btn = PushButton("Salvar Chave", provider_card)
        self.save_key_btn.clicked.connect(self._save_key)
        key_btn_row.addWidget(self.save_key_btn)

        self.check_key_btn = PushButton("Validar Chave do Provedor", provider_card)
        self.check_key_btn.clicked.connect(self._validate_key)
        key_btn_row.addWidget(self.check_key_btn)
        key_btn_row.addStretch(1)
        provider_layout.addLayout(key_btn_row)

        key_info = CaptionLabel(
            "🔒 As chaves são armazenadas com criptografia segura no Gerenciador de Credenciais do Windows (Keyring).",
            provider_card,
        )
        key_info.setWordWrap(True)
        key_info.setStyleSheet("color: rgba(200, 200, 200, 0.7);")
        provider_layout.addWidget(key_info)

        self.cards_layout.addWidget(provider_card)

        # ----------------------------------------------------------------------
        # Card 2: Performance Profile
        # ----------------------------------------------------------------------
        perf_card = SimpleCardWidget(self.cards_container)
        perf_layout = QVBoxLayout(perf_card)
        perf_layout.setContentsMargins(16, 14, 16, 14)
        perf_layout.setSpacing(10)

        perf_title = StrongBodyLabel("Perfil de Desempenho do Sistema", perf_card)
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
        perf_layout.addWidget(self.desc_label)

        self.apply_btn = PrimaryPushButton("Aplicar e Reiniciar Jarvis", perf_card)
        self.apply_btn.setVisible(False)
        self.apply_btn.clicked.connect(self._apply_and_restart)
        perf_layout.addWidget(self.apply_btn)

        self.slider.valueChanged.connect(self._on_slider_changed)
        self._update_slider_text(self.slider.value())

        self.cards_layout.addWidget(perf_card)

        # ----------------------------------------------------------------------
        # Card 3: Location (Sem o "Preferências", conforme solicitado)
        # ----------------------------------------------------------------------
        loc_card = SimpleCardWidget(self.cards_container)
        loc_layout = QVBoxLayout(loc_card)
        loc_layout.setContentsMargins(16, 14, 16, 14)
        loc_layout.setSpacing(10)

        loc_title = StrongBodyLabel("Localização", loc_card)
        loc_layout.addWidget(loc_title)

        loc_row = QHBoxLayout()
        loc_row.setSpacing(8)
        loc_lbl = BodyLabel("Cidade Padrão (Clima):", loc_card)
        loc_lbl.setFixedWidth(145)
        loc_row.addWidget(loc_lbl)

        self.city_input = FluentLineEdit(loc_card)
        self.city_input.setPlaceholderText("Ex: Itamonte, São Paulo, Curitiba...")
        self.city_input.setClearButtonEnabled(True)
        self.city_input.setMinimumWidth(180)
        self.city_input.setMaximumWidth(260)
        current_city = (
            config.get("tools", {}).get("weather", {}).get("default_city", "São Paulo")
        )
        self.city_input.setText(str(current_city))
        loc_row.addWidget(self.city_input)

        self.save_city_btn = PrimaryPushButton("Salvar Cidade", loc_card)
        self.save_city_btn.clicked.connect(self._save_city)
        loc_row.addWidget(self.save_city_btn)
        loc_row.addStretch(1)
        loc_layout.addLayout(loc_row)

        loc_info = CaptionLabel(
            "💡 Usada automaticamente em consultas de previsão do tempo ('como tá o tempo?') quando nenhuma cidade for especificada.",
            loc_card,
        )
        loc_info.setWordWrap(True)
        loc_info.setStyleSheet("color: rgba(200, 200, 200, 0.7);")
        loc_layout.addWidget(loc_info)

        self.cards_layout.addWidget(loc_card)

        # ----------------------------------------------------------------------
        # Card 4: System Updates
        # ----------------------------------------------------------------------
        self.update_mgr = UpdateManager()
        self.pref_mgr = UpdatePreferenceManager()
        self._latest_release: ReleaseInfo | None = None

        self.update_checked.connect(self._on_update_check_finished)
        self.update_progress.connect(self._on_update_progress)
        self.update_extracting.connect(self._on_update_extracting)
        self.update_download_finished.connect(self._on_download_finished)
        self.update_failed.connect(self._on_update_failed)

        update_card = SimpleCardWidget(self.cards_container)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(16, 14, 16, 14)
        update_layout.setSpacing(10)

        update_title = StrongBodyLabel("Atualizações do Sistema", update_card)
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

        self.cards_layout.addWidget(update_card)

        self.scroll_area.setWidget(self.cards_container)
        main_layout.addWidget(self.scroll_area)

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

    def _save_city(self) -> None:
        city = self.city_input.text().strip()
        if not city:
            InfoBar.warning(
                title="Atenção",
                content="Por favor, informe um nome de cidade válido.",
                parent=self,
                duration=3000,
            )
            return

        if "tools" not in config:
            config["tools"] = {}
        if "weather" not in config["tools"]:
            config["tools"]["weather"] = {}

        config["tools"]["weather"]["default_city"] = city
        try:
            update_yaml_weather_city(city)
        except Exception as e:
            logger.warning(f"Could not persist default city to yaml: {e}")

        InfoBar.success(
            title="Sucesso",
            content=f"Cidade padrão atualizada para '{city}'.",
            parent=self,
            duration=3000,
        )
        logger.info(f"Updated default weather city to '{city}' via SettingsTab.")

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
