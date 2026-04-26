import subprocess
import threading
from typing import Optional
from core.logger_config import logger
from core.security_ui import SecurityDialog
from core.audio_engine import record_command_audio
from core.stt_engine import stt_engine
from core.utils import normalize_text
from core.plugin_manager import plugin_manager
from core.history_db import history_manager
from core.state import state_manager, JarvisState
from core.execution_plan import ExecutionPlan, ExecutionStep, StepType, RiskLevel

class ActionDispatcher:
    def __init__(self, config, automator, audio_stream=None):
        self.config = config
        self.automator = automator
        self.audio_stream = audio_stream
        self.last_input_text = "N/A"
        self.last_input_source = "voice"
        self.last_confidence = 1.0
        self.waiting_for_auth = False
        self.active_dialog: Optional[SecurityDialog] = None # Access for main.py voice confirmation
        self.last_plan: Optional[ExecutionPlan] = None

    def handle_plan(self, plan: ExecutionPlan):
        """Processes an ExecutionPlan, including validation and user confirmation."""
        logger.info(f"Handling execution plan: {plan.intent} (Risk: {plan.global_risk.value})")
        
        # 1. Prompt Guard Validation
        from core.prompt_guard import PromptGuard
        sanitized_dict = PromptGuard.sanitize_output(plan.to_dict())
        plan = ExecutionPlan.from_dict(sanitized_dict)

        if plan.global_risk == RiskLevel.BLOCKED:
            logger.warning("Plan blocked by PromptGuard!")
            self.automator.speak("Ação bloqueada por segurança.")
            return False

        # 2. Check if Dry-run is needed
        dry_run_config = self.config.get('dry_run', {})
        require_confirmation = dry_run_config.get('enabled', True)
        
        if plan.global_risk == RiskLevel.SAFE and dry_run_config.get('bypass_for_safe_intents', True):
            require_confirmation = False

        if require_confirmation:
            if not self._confirm_dry_run(plan):
                logger.info("Plan rejected by user.")
                return False

        # 3. Execute
        return self.execute_plan(plan)

    def _confirm_dry_run(self, plan: ExecutionPlan) -> bool:
        """Requests user confirmation for the execution plan."""
        logger.info(f"Requesting confirmation for plan: {plan.intent}")
        state_manager.set_state(JarvisState.CONFIRMING_DRY_RUN, context={"plan": plan.to_dict()})
        
        self.automator.speak(f"Planejo o seguinte: {plan.explanation}. Posso executar?")
        
        action_desc = f"{plan.intent.upper()}\n\n{plan.explanation}\n\nSteps:\n" + \
                     "\n".join([f"- {s.type.value}: {s.description or ''}" for s in plan.steps])
        
        self.active_dialog = SecurityDialog(action_desc)
        self.waiting_for_auth = True
        
        # UI blocks here (main.py now handles the voice confirmation via active_dialog)
        result = self.active_dialog.ask()
        
        self.waiting_for_auth = False
        self.active_dialog = None
        return result

    def execute_plan(self, plan: ExecutionPlan):
        """Executes an ExecutionPlan step by step with isolation."""
        logger.info(f"Starting execution of plan: {plan.intent}")
        state_manager.set_state(JarvisState.EXECUTING, context={"intent": plan.intent})
        self.last_plan = plan
        
        try:
            for i, step in enumerate(plan.steps):
                logger.info(f"Step {i+1}/{len(plan.steps)}: {step.type.value} - {step.description or ''}")
                
                success = self._execute_step(step)
                if not success:
                    logger.error(f"Step {i+1} failed. Aborting plan.")
                    state_manager.set_state(JarvisState.ERROR, context={"error": f"Step {i+1} failed: {step.type.value}"})
                    history_manager.log_execution(self.last_input_text, self.last_input_source, plan.intent, plan.global_risk.value, "failed", confidence=self.last_confidence, error_msg=f"Failed at step {i+1}")
                    return False
                
            logger.info("Plan executed successfully.")
            history_manager.log_execution(self.last_input_text, self.last_input_source, plan.intent, plan.global_risk.value, "success", confidence=self.last_confidence)
            self.automator.speak("Pronto!")
            return True
        except Exception as e:
            logger.error(f"Critical error during plan execution: {e}")
            state_manager.set_state(JarvisState.ERROR, context={"error": str(e)})
            return False

    def _execute_step(self, step: ExecutionStep) -> bool:
        """Executes a single step based on its type."""
        try:
            if step.type == StepType.COMMAND:
                cmd = step.payload.get("command")
                subprocess.run(["cmd", "/c", cmd], shell=False, check=True)
                return True
            elif step.type == StepType.OPEN_APP:
                target = step.payload.get("target")
                import os
                os.startfile(target)
                return True
            elif step.type == StepType.WRITE:
                text = step.payload.get("text")
                self.automator.type_text(text)
                return True
            elif step.type == StepType.NAVIGATE:
                target = step.payload.get("target")
                subprocess.run(["cmd", "/c", f"cd /d {target}"], shell=False, check=True)
                return True
            elif step.type == StepType.WAIT:
                duration = step.payload.get("duration", 1.0)
                import time
                time.sleep(float(duration))
                return True
            return False
        except Exception as e:
            logger.error(f"Step execution error ({step.type.value}): {e}")
            return False

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
            state_manager.set_state(JarvisState.CONFIRMING_DRY_RUN, context={"intent": intent})
            
            self.automator.speak("Ação perigosa detectada. Deseja autorizar?")
            
            action_desc = action_config.get('description', action_config.get('intent', action_config.get('action', 'Ação do sistema')))
            self.active_dialog = SecurityDialog(action_desc)
            self.waiting_for_auth = True
            
            result = self.active_dialog.ask()
            
            self.waiting_for_auth = False
            self.active_dialog = None
            
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
        """Legacy handler for non-ExecutionPlan actions."""
        logger.info(f"Dispatching dynamic action: {action_config}")
        if not self._check_authorization(action_config): return
            
        type_hint = action_config.get('type', 'action')
        if type_hint == 'chat':
            self.automator.speak(action_config.get('message', 'Sem resposta.'))
            return

        action_type = action_config.get('action')
        if action_type == 'warp': self._handle_warp(action_config)
        elif action_type == 'system': self._handle_system(action_config)
        elif action_type == 'plugin': self._handle_plugin(action_config)

    def _handle_warp(self, action_config):
        state_manager.set_state(JarvisState.EXECUTING)
        default_warp_path = self.config.get('integrations', {}).get('warp', {}).get('path', self.automator.warp_path)
        self.automator.warp_path = action_config.get('warp_path', default_warp_path)
        self.automator.commands = action_config.get('commands', [])        
        try:
            self.automator.run_workflow()
            history_manager.log_execution(self.last_input_text, self.last_input_source, "warp_workflow", "safe", "success", confidence=self.last_confidence)
        except Exception as e:
            history_manager.log_execution(self.last_input_text, self.last_input_source, "warp_workflow", "safe", "error", confidence=self.last_confidence, error_msg=str(e))
        
    def _handle_system(self, action_config):
        state_manager.set_state(JarvisState.EXECUTING)
        commands = action_config.get('commands', [])
        risk_level = action_config.get('risk_level', 'safe')
        for cmd in commands:
            try:
                subprocess.run(["cmd", "/c", cmd], shell=False, check=True)
            except Exception as e:
                logger.error(f"Error executing system command: {e}")
                history_manager.log_execution(self.last_input_text, self.last_input_source, "system_cmd", risk_level, "error", confidence=self.last_confidence, error_msg=str(e))
                return
        self.automator.speak("Pronto!")

    def _handle_plugin(self, action_config):
        state_manager.set_state(JarvisState.EXECUTING)
        intent_name = action_config.get('intent')
        actions = plugin_manager.get_actions_for_intent(intent_name)
        if not actions: return
        for action in actions:
            a_type = action.get('type')
            try:
                if a_type == 'system_open': os.startfile(action.get('target'))
                elif a_type == 'wait': time.sleep(float(action.get('duration', 1.0)))
                elif a_type == 'keyboard_shortcut': pyautogui.hotkey(*action.get('keys', []))
                elif a_type == 'type_and_enter':
                    self.automator.type_text(action.get('text', ''))
                    pyautogui.press('enter')
                elif a_type == 'system_exec': subprocess.run(["cmd", "/c", action.get('command', '')], shell=False, check=True)
            except Exception as e:
                logger.error(f"Error executing plugin action: {e}")
                return
        self.automator.speak("Pronto!")
