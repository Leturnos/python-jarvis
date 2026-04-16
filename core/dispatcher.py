import subprocess
from core.logger_config import logger

class ActionDispatcher:
    def __init__(self, config, automator):
        self.config = config
        self.automator = automator

    def handle(self, wakeword_name):
        logger.info(f"Dispatching action for: {wakeword_name}")
        wakewords = self.config.get('wakewords', {})
        
        if wakeword_name not in wakewords:
            logger.error(f"No configuration found for wakeword: {wakeword_name}")
            self.automator.speak("Comando não configurado.")
            return
            
        action_config = wakewords[wakeword_name]
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