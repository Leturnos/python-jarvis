import subprocess
import threading
import json
import os
import time
import pyautogui
from typing import Optional
from core.logger_config import logger
from core.security_ui import SecurityDialog
from core.audio_engine import record_command_audio
from core.stt_engine import stt_engine
from core.utils import normalize_text
from core.plugin_manager import plugin_manager
from core.history_db import history_manager
from core.macro_manager import macro_manager
from core.state import state_manager, JarvisState
from core.execution_plan import ExecutionPlan, ExecutionStep, StepType, RiskLevel
from core.errors import BusinessError

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
        
        action_json = json.dumps(plan.to_dict())
        
        try:
            for i, step in enumerate(plan.steps):
                logger.info(f"Step {i+1}/{len(plan.steps)}: {step.type.value} - {step.description or ''}")
                
                success = self._execute_step(step)
                if not success:
                    logger.error(f"Step {i+1} failed. Aborting plan.")
                    state_manager.set_state(JarvisState.ERROR, context={"error": f"Step {i+1} failed: {step.type.value}"})
                    history_manager.log_execution(self.last_input_text, self.last_input_source, plan.intent, plan.global_risk.value, "failed", confidence=self.last_confidence, error_msg=f"Failed at step {i+1}", action_json=action_json)
                    return False
                
            logger.info("Plan executed successfully.")
            history_manager.log_execution(self.last_input_text, self.last_input_source, plan.intent, plan.global_risk.value, "success", confidence=self.last_confidence, action_json=action_json)
            self.automator.speak("Pronto!")
            return True
        except Exception as e:
            logger.error(f"Critical error during plan execution: {e}")
            state_manager.set_state(JarvisState.ERROR, context={"error": str(e)})
            return False

    def replay_last_command(self) -> bool:
        """Fetches the last successful action from history and executes it again."""
        logger.info("Replaying last successful command...")
        last_json = history_manager.get_last_successful_json()
        
        if not last_json:
            logger.warning("No successful command found in history to replay.")
            self.automator.speak("Não encontrei nenhuma ação recente para repetir.")
            raise BusinessError("No successful command found in history to replay.")
            
        try:
            data = json.loads(last_json)
            plan = ExecutionPlan.from_dict(data)
            logger.info(f"Reconstructing plan for replay: {plan.intent}")
            
            # Use handle_plan to trigger confirmation if needed for the replay
            return self.handle_plan(plan)
        except Exception as e:
            logger.error(f"Error during replay reconstruction: {e}")
            self.automator.speak("Erro ao repetir a última ação.")
            return False

    def initiate_macro_creation(self, n=3):
        """Flow to create a macro from the last N actions."""
        logger.info(f"Initiating macro creation from last {n} actions.")
        recent_jsons = history_manager.get_recent_history_json(n)
        
        if not recent_jsons:
            self.automator.speak("Não encontrei ações recentes suficientes para criar uma macro.")
            raise BusinessError(f"Insufficient history (requested {n} items).")

        # 1. Use MacroManager to propose a plan
        plan = macro_manager.create_macro_from_recent(recent_jsons)
        
        if not plan:
            self.automator.speak("Erro ao gerar a macro inteligente.")
            return False

        # 2. Use the existing dry-run confirmation logic
        # This will show the UI, speak the explanation, and wait for Yes/No
        if self._confirm_dry_run(plan):
            # 3. If approved, save as plugin
            success = macro_manager.save_macro_as_plugin(plan)
            if success:
                self.automator.speak(f"Macro '{plan.intent}' salva com sucesso!")
                return True
            else:
                self.automator.speak("Erro ao salvar o arquivo da macro.")
                return False
        
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
                time.sleep(float(duration))
                return True
            elif step.type == StepType.HOTKEY:
                keys = step.payload.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
                return True
            elif step.type == StepType.TYPE_AND_ENTER:
                self.automator.type_text(step.payload.get("text", ""))
                pyautogui.press('enter')
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
        """Legacy handler for non-ExecutionPlan actions. Chat responses are NOT logged as executable actions."""
        logger.info(f"Dispatching dynamic action: {action_config}")
        
        type_hint = action_config.get('type', 'action')
        if type_hint == 'chat':
            self.automator.speak(action_config.get('message', 'Sem resposta.'))
            # Chat is logged as context, but action_json (executable) is None
            history_manager.log_execution(self.last_input_text, self.last_input_source, "chat", "safe", "success", confidence=self.last_confidence)
            return

        if not self._check_authorization(action_config): return
            
        action_type = action_config.get('action')
        if action_type == 'warp': self._handle_warp(action_config)
        elif action_type == 'system': self._handle_system(action_config)
        elif action_type == 'plugin': self._handle_plugin(action_config)

    def _handle_warp(self, action_config):
        default_warp_path = self.config.get('integrations', {}).get('warp', {}).get('path', self.automator.warp_path)
        warp_path = action_config.get('warp_path', default_warp_path)
        commands = action_config.get('commands', [])
        
        steps = []
        steps.append(ExecutionStep(type=StepType.OPEN_APP, payload={"target": warp_path}, description="Open Terminal"))
        steps.append(ExecutionStep(type=StepType.WAIT, payload={"duration": 2.0}, description="Wait for Terminal to load"))
        steps.append(ExecutionStep(type=StepType.HOTKEY, payload={"keys": ["ctrl", "shift", "t"]}, description="Open new tab"))
        steps.append(ExecutionStep(type=StepType.WAIT, payload={"duration": 1.2}, description="Wait for tab animation"))
        
        for cmd in commands:
            steps.append(ExecutionStep(type=StepType.TYPE_AND_ENTER, payload={"text": cmd}, description=f"Run: {cmd}"))
            steps.append(ExecutionStep(type=StepType.WAIT, payload={"duration": 0.5}, description="Wait for command"))
            
        plan = ExecutionPlan(
            intent=action_config.get('intent', 'warp_workflow'),
            explanation="Iniciando fluxo de trabalho no terminal",
            steps=steps,
            global_risk=RiskLevel.SAFE,
            schema_version="1.1"
        )
        self.execute_plan(plan)
        
    def _handle_system(self, action_config):
        commands = action_config.get('commands', [])
        risk_level_str = action_config.get('risk_level', 'safe')
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.SAFE
            
        steps = [ExecutionStep(type=StepType.COMMAND, payload={"command": cmd}, description=f"Execute: {cmd}") for cmd in commands]
        
        plan = ExecutionPlan(
            intent=action_config.get('intent', 'system_cmd'),
            explanation="Executando comando de sistema",
            steps=steps,
            global_risk=risk_level,
            schema_version="1.1"
        )
        self.execute_plan(plan)

    def _handle_plugin(self, action_config):
        intent_name = action_config.get('intent')
        actions = plugin_manager.get_actions_for_intent(intent_name)
        if not actions: return
        
        steps = []
        for action in actions:
            a_type = action.get('type')
            if a_type == 'system_open':
                steps.append(ExecutionStep(type=StepType.OPEN_APP, payload={"target": action.get('target')}))
            elif a_type == 'wait':
                steps.append(ExecutionStep(type=StepType.WAIT, payload={"duration": action.get('duration', 1.0)}))
            elif a_type == 'keyboard_shortcut':
                steps.append(ExecutionStep(type=StepType.HOTKEY, payload={"keys": action.get('keys', [])}))
            elif a_type == 'type_and_enter':
                steps.append(ExecutionStep(type=StepType.TYPE_AND_ENTER, payload={"text": action.get('text', '')}))
            elif a_type == 'system_exec':
                steps.append(ExecutionStep(type=StepType.COMMAND, payload={"command": action.get('command', '')}))
        
        risk_level_str = action_config.get('risk_level', 'safe')
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.SAFE

        plan = ExecutionPlan(
            intent=intent_name,
            explanation=f"Executando plugin: {intent_name}",
            steps=steps,
            global_risk=risk_level,
            schema_version="1.1"
        )
        self.execute_plan(plan)
