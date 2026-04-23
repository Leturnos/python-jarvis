import subprocess
import threading
from core.logger_config import logger
from core.security_ui import SecurityDialog
from core.audio_engine import record_command_audio
from core.stt_engine import stt_engine
from core.utils import normalize_text
from core.plugin_manager import plugin_manager
from core.history_db import history_manager

class ActionDispatcher:
    def __init__(self, config, automator, audio_stream=None):
        self.config = config
        self.automator = automator
        self.audio_stream = audio_stream
        self.last_input_text = "N/A"
        self.last_input_source = "voice"
        self.last_confidence = 1.0

    def _check_authorization(self, action_config):
        risk_level = action_config.get('risk_level', 'safe')
        intent = action_config.get('intent', action_config.get('action', 'unknown'))
        
        if risk_level == 'blocked':
            logger.warning("Blocked action detected!")
            self.automator.speak("Atenção: Ação catastrófica detectada. Comando bloqueado por segurança.")
            history_manager.log_execution(self.last_input_text, self.last_input_source, intent, risk_level, "blocked", confidence=self.last_confidence, error_msg="Policy Blocked")
            return False
            
        if risk_level == 'dangerous':
            logger.warning("Dangerous action detected! Requesting authorization...")
            self.automator.speak("Ação perigosa detectada. Deseja autorizar? Diga Sim ou Não, ou use a janela na tela.")
            
            action_desc = action_config.get('description', action_config.get('action', 'Ação do sistema'))
            dialog = SecurityDialog(action_desc)
            
            # Voice Integration in background
            def listen_for_confirmation(dialog, stream):
                import numpy as np
                if not stream:
                    logger.error("No audio stream available for voice confirmation.")
                    return
                    
                while not dialog.confirmed_event.is_set():
                    try:
                        # Flush the buffer to discard old audio/TTS
                        if stream.get_read_available() > 0:
                            try:
                                stream.read(stream.get_read_available(), exception_on_overflow=False)
                            except Exception:
                                pass

                        audio = record_command_audio(stream, max_seconds=4, stop_event=dialog.confirmed_event)
                        
                        if dialog.confirmed_event.is_set():
                            break
                            
                        pcm = np.frombuffer(audio, dtype=np.int16)
                        if len(pcm) == 0 or np.max(np.abs(pcm)) < 200:
                            continue # Try again if silent
                            
                        text = stt_engine.transcribe(audio)
                        norm = normalize_text(text)
                        
                        logger.info(f"Voice confirmation attempt: '{norm}'")
                        
                        if any(word in norm for word in ["sim", "confirma", "pode", "autorizo", "yes"]):
                            logger.info("Voice confirmation: APPROVED")
                            dialog.result = True
                            dialog.close()
                            break
                        elif any(word in norm for word in ["nao", "não", "cancela", "aborta", "no"]):
                            logger.info("Voice confirmation: REJECTED")
                            dialog.result = False
                            dialog.close()
                            break
                    except Exception as e:
                        logger.error(f"Error in voice confirmation thread: {e}")
                        break

            voice_thread = threading.Thread(
                target=listen_for_confirmation, 
                args=(dialog, self.audio_stream),
                daemon=True
            )
            voice_thread.start()
            
            # UI blocks here
            result = dialog.ask()
            if not result:
                history_manager.log_execution(self.last_input_text, self.last_input_source, intent, risk_level, "denied", confidence=self.last_confidence, error_msg="User Refused")
            return result
            
        return True

    def handle(self, wakeword_name, confidence=1.0):
        logger.info(f"Dispatching action for: {wakeword_name}")
        self.last_confidence = confidence
        wakewords = self.config.get('wakewords', {})
        
        if wakeword_name not in wakewords:
            logger.error(f"No configuration found for wakeword: {wakeword_name}")
            self.automator.speak("Comando não configurado.")
            return
            
        action_config = wakewords[wakeword_name]

        if not self._check_authorization(action_config):
            return

        action_type = action_config.get('action')
        
        if action_type == 'warp':
            self._handle_warp(action_config)
        elif action_type == 'system':
            self._handle_system(action_config)
        elif action_type == 'plugin':
            self._handle_plugin(action_config)
        else:
            logger.error(f"Unknown action: {action_type}")
            self.automator.speak("Tipo de ação desconhecida.")

    def handle_dynamic(self, action_config):
        """Executes a dynamically generated action dictionary from the LLM."""
        logger.info(f"Dispatching dynamic action: {action_config}")
        
        if not action_config or not isinstance(action_config, dict):
            logger.error("Invalid dynamic action config.")
            self.automator.speak("Não consegui processar a ação.")
            return

        if not self._check_authorization(action_config):
            return
            
        type_hint = action_config.get('type', 'action')
        
        if type_hint == 'chat':
            message = action_config.get('message', 'Sem resposta.')
            self.automator.speak(message)
            return

        action_type = action_config.get('action')

        if action_type == 'warp':
            self._handle_warp(action_config)
        elif action_type == 'system':
            self._handle_system(action_config)
        elif action_type == 'plugin':
            self._handle_plugin(action_config)
        else:
            logger.error(f"Unknown action in dynamic config: {action_type}")
            self.automator.speak("Ação dinâmica desconhecida.")

    def _handle_warp(self, action_config):
        # Update automator config dynamically before running
        default_warp_path = self.config.get('integrations', {}).get('warp', {}).get('path', self.automator.warp_path)
        self.automator.warp_path = action_config.get('warp_path', default_warp_path)
        self.automator.commands = action_config.get('commands', [])        
        try:
            self.automator.run_workflow()
            history_manager.log_execution(self.last_input_text, self.last_input_source, "warp_workflow", "safe", "success", confidence=self.last_confidence)
        except Exception as e:
            history_manager.log_execution(self.last_input_text, self.last_input_source, "warp_workflow", "safe", "error", confidence=self.last_confidence, error_msg=str(e))
        
    def _handle_system(self, action_config):
        commands = action_config.get('commands', [])
        risk_level = action_config.get('risk_level', 'safe')
        logger.info("Executing system commands...")
        
        for cmd in commands:
            logger.info(f"Running: {cmd}")
            try:
                subprocess.run(["cmd", "/c", cmd], shell=False, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Command failed with exit code {e.returncode}: {cmd}")
                self.automator.speak("Erro ao executar comando do sistema.")
                history_manager.log_execution(self.last_input_text, self.last_input_source, "system_cmd", risk_level, "failed", confidence=self.last_confidence, error_msg=str(e))
                return
            except Exception as e:
                logger.error(f"Error executing system command: {e}")
                self.automator.speak("Erro ao executar comando do sistema.")
                history_manager.log_execution(self.last_input_text, self.last_input_source, "system_cmd", risk_level, "error", confidence=self.last_confidence, error_msg=str(e))
                return
                
        logger.info("System commands executed successfully.")
        history_manager.log_execution(self.last_input_text, self.last_input_source, "system_cmd", risk_level, "success", confidence=self.last_confidence)
        self.automator.speak("Pronto!")

    def _handle_plugin(self, action_config):
        intent_name = action_config.get('intent')
        risk_level = action_config.get('risk_level', 'safe')
        
        if not intent_name:
            logger.error("No intent provided for plugin action.")
            self.automator.speak("Ação de plugin sem intenção definida.")
            return

        actions = plugin_manager.get_actions_for_intent(intent_name)
        if not actions:
            logger.error(f"No actions found for intent: {intent_name}")
            self.automator.speak("Comando de plugin não encontrado.")
            history_manager.log_execution(self.last_input_text, self.last_input_source, intent_name, risk_level, "failed", confidence=self.last_confidence, error_msg="Intent not found")
            return

        logger.info(f"Executing plugin actions for intent: {intent_name}")
        for action in actions:
            a_type = action.get('type')
            try:
                if a_type == 'system_open':
                    target = action.get('target')
                    logger.info(f"system_open: {target}")
                    import os
                    os.startfile(target)
                elif a_type == 'wait':
                    duration = action.get('duration', 1.0)
                    import time
                    time.sleep(float(duration))
                elif a_type == 'keyboard_shortcut':
                    keys = action.get('keys', [])
                    import pyautogui
                    pyautogui.hotkey(*keys)
                elif a_type == 'type_and_enter':
                    text = action.get('text', '')
                    self.automator.type_text(text)
                    import pyautogui
                    pyautogui.press('enter')
                elif a_type == 'system_exec':
                    command = action.get('command', '')
                    logger.info(f"system_exec: {command}")
                    subprocess.run(["cmd", "/c", command], shell=False, check=True)
                else:
                    logger.warning(f"Unknown plugin action type: {a_type}")
            except Exception as e:
                logger.error(f"Error executing plugin action {a_type}: {e}")
                self.automator.speak("Ocorreu um erro ao executar a automação.")
                history_manager.log_execution(self.last_input_text, self.last_input_source, intent_name, risk_level, "error", confidence=self.last_confidence, error_msg=str(e))
                return

        history_manager.log_execution(self.last_input_text, self.last_input_source, intent_name, risk_level, "success", confidence=self.last_confidence)
        self.automator.speak("Pronto!")