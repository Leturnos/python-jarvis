import subprocess
import threading
from core.logger_config import logger
from core.security_ui import SecurityDialog
from core.audio_engine import record_command_audio
from core.stt_engine import stt_engine
from core.utils import normalize_text

class ActionDispatcher:
    def __init__(self, config, automator, audio_stream=None):
        self.config = config
        self.automator = automator
        self.audio_stream = audio_stream

    def _check_authorization(self, action_config):
        risk_level = action_config.get('risk_level', 'safe')
        
        if risk_level == 'blocked':
            logger.warning("Blocked action detected!")
            self.automator.speak("Atenção: Ação catastrófica detectada. Comando bloqueado por segurança.")
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
            return result
            
        return True

    def handle(self, wakeword_name):
        logger.info(f"Dispatching action for: {wakeword_name}")
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
        else:
            logger.error(f"Unknown action in dynamic config: {action_type}")
            self.automator.speak("Ação dinâmica desconhecida.")

    def _handle_warp(self, action_config):
        # Update automator config dynamically before running
        default_warp_path = self.config.get('integrations', {}).get('warp', {}).get('path', self.automator.warp_path)
        self.automator.warp_path = action_config.get('warp_path', default_warp_path)
        self.automator.commands = action_config.get('commands', [])        
        self.automator.run_workflow()
        
    def _handle_system(self, action_config):
        commands = action_config.get('commands', [])
        logger.info("Executing system commands...")
        
        for cmd in commands:
            logger.info(f"Running: {cmd}")
            try:
                # Use subprocess to run system commands
                subprocess.run(cmd, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Command failed with exit code {e.returncode}: {cmd}")
                self.automator.speak("Erro ao executar comando do sistema.")
                return
            except Exception as e:
                logger.error(f"Error executing system command: {e}")
                self.automator.speak("Erro ao executar comando do sistema.")
                return
                
        logger.info("System commands executed successfully.")
        self.automator.speak("Pronto!")