"""Core dispatching logic for Jarvis actions.

This module contains the ActionDispatcher class, which is responsible for
orchestrating the execution of both static (wakeword-based) and dynamic
(LLM-based) actions, while ensuring security through user confirmation.
"""

import json
import os
import subprocess
import time
from typing import Optional

import pyautogui

from core.execution.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    RiskLevel,
    StepType,
)
from core.infra.logger_config import logger
from core.persistence.history_db import history_manager
from core.plugins.macro_manager import macro_manager
from core.plugins.plugin_manager import plugin_manager
from core.runtime.state import JarvisState, state_manager
from core.shared.errors import BusinessError
from core.shared.utils import time_it
from core.ui.security_ui import SecurityDialog


class ActionDispatcher:
    """Central hub for coordinating action execution, security validation, and routing.

    The ActionDispatcher receives instructions (either from wake words or dynamic LLM analysis),
    converts them into execution plans (if not already structured), validates them against
    security policies (PromptGuard), requests user authorization when necessary, and
    orchestrates the step-by-step execution.

    Attributes:
        config (dict): Global application configuration.
        automator (WarpAutomator): Interface for UI automation and speech synthesis.
        audio_stream: The current PyAudio input stream.
        last_input_text (str): The last transcribed text or command name.
        last_input_source (str): Source of the command ('voice', 'text', 'shortcut').
        last_confidence (float): Confidence score of the last wake word detection.
        waiting_for_auth (bool): Whether the dispatcher is currently blocked waiting for UI/voice approval.
        active_dialog (Optional[SecurityDialog]): Reference to the currently visible security popup.
        last_plan (Optional[ExecutionPlan]): The most recently executed or proposed plan.
    """

    def __init__(self, config, automator, audio_stream=None):
        """Initializes the ActionDispatcher with its dependencies.

        Args:
            config (dict): The configuration dictionary.
            automator (WarpAutomator): The UI automation helper.
            audio_stream (optional): The PyAudio stream for secondary recording tasks.
        """
        self.config = config
        self.automator = automator
        self.audio_stream = audio_stream
        self.last_input_text = "N/A"
        self.last_input_source = "voice"
        self.last_confidence = 1.0
        self.waiting_for_auth = False
        self.active_dialog: Optional[SecurityDialog] = (
            None  # Access for main.py voice confirmation
        )
        self.last_plan: Optional[ExecutionPlan] = None

    def handle_plan(self, plan: ExecutionPlan) -> bool:
        """Processes an ExecutionPlan, including validation and user confirmation.

        This is the main entry point for structured execution. it handles security
        sanitization via PromptGuard, determines if a dry-run confirmation is required
        based on the risk level and config, and finally delegates to execute_plan.

        Args:
            plan (ExecutionPlan): The structured plan to be processed.

        Returns:
            bool: True if the plan was successfully executed, False if blocked,
                rejected, or if execution failed.
        """
        logger.info(
            f"Handling execution plan: {plan.intent} (Risk: {plan.global_risk.value})"
        )

        if plan.intent == "explain_last_action":
            self._handle_explain_last_action()
            return True

        # Handle built-in system states
        if plan.intent in ("sleep", "dormir", "parar_de_ouvir", "stop_listening"):
            logger.info("System command: Entering SLEEPING state.")
            self.automator.speak(
                "Indo dormir. Use o atalho ou a bandeja para me acordar."
            )
            state_manager.set_state(JarvisState.SLEEPING)
            return True

        if plan.intent in ("mute", "silenciar"):
            logger.info("System command: Entering MUTED state.")
            self.automator.speak("Silenciado.")
            state_manager.set_state(JarvisState.MUTED)
            return True

        # 1. Prompt Guard Validation
        from core.ai.prompt_guard import PromptGuard

        sanitized_dict = PromptGuard.sanitize_output(plan.to_dict())
        plan = ExecutionPlan.from_dict(sanitized_dict)

        if plan.global_risk == RiskLevel.BLOCKED:
            logger.warning("Plan blocked by PromptGuard!")
            self.automator.speak("Ação bloqueada por segurança.")
            return False

        # 2. Check if Dry-run is needed
        dry_run_config = self.config.get("dry_run", {})
        require_confirmation = dry_run_config.get("enabled", True)

        if plan.global_risk == RiskLevel.SAFE and dry_run_config.get(
            "bypass_for_safe_intents", True
        ):
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
        state_manager.set_state(
            JarvisState.CONFIRMING_DRY_RUN, context={"plan": plan.to_dict()}
        )

        self.automator.speak(f"Planejo o seguinte: {plan.explanation}. Posso executar?")

        action_desc = (
            f"{plan.intent.upper()}\n\n{plan.explanation}\n\nSteps:\n"
            + "\n".join(
                [f"- {s.type.value}: {s.description or ''}" for s in plan.steps]
            )
        )

        self.active_dialog = SecurityDialog(action_desc)
        self.waiting_for_auth = True

        # UI blocks here (main.py now handles the voice confirmation via active_dialog)
        result = self.active_dialog.ask()

        self.waiting_for_auth = False
        self.active_dialog = None
        return result

    @time_it
    def execute_plan(self, plan: ExecutionPlan) -> bool:
        """Executes an ExecutionPlan step by step with isolation.

        Each step in the plan is executed sequentially. If any step fails, the
        entire plan is aborted, the failure is logged, and the user is notified.

        Args:
            plan (ExecutionPlan): The validated plan to execute.

        Returns:
            bool: True if all steps were executed successfully, False otherwise.
        """
        logger.info(f"Starting execution of plan: {plan.intent}")
        state_manager.set_state(JarvisState.EXECUTING, context={"intent": plan.intent})
        self.last_plan = plan

        action_json = json.dumps(plan.to_dict())

        try:
            for i, step in enumerate(plan.steps):
                logger.info(
                    f"Step {i + 1}/{len(plan.steps)}: {step.type.value} - {step.description or ''}"
                )

                success = self._execute_step(step)
                if not success:
                    logger.error(f"Step {i + 1} failed. Aborting plan.")
                    state_manager.set_state(
                        JarvisState.ERROR,
                        context={"error": f"Step {i + 1} failed: {step.type.value}"},
                    )
                    history_manager.log_execution(
                        self.last_input_text,
                        self.last_input_source,
                        plan.intent,
                        plan.global_risk.value,
                        "failed",
                        confidence=self.last_confidence,
                        error_msg=f"Failed at step {i + 1}",
                        action_json=action_json,
                    )
                    return False

            logger.info("Plan executed successfully.")
            history_manager.log_execution(
                self.last_input_text,
                self.last_input_source,
                plan.intent,
                plan.global_risk.value,
                "success",
                confidence=self.last_confidence,
                action_json=action_json,
            )
            self.automator.speak("Pronto!")
            return True
        except Exception as e:
            logger.error(f"Critical error during plan execution: {e}")
            state_manager.set_state(JarvisState.ERROR, context={"error": str(e)})
            return False

    def replay_last_command(self) -> bool:
        """Fetches the last successful action from history and executes it again.

        This method retrieves the most recent successful execution plan from the
        SQLite database, reconstructs it, and triggers a new execution via handle_plan.

        Returns:
            bool: True if the replay was successful, False otherwise.

        Raises:
            BusinessError: If no recent successful commands are found in history.
        """
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

    def initiate_macro_creation(self, n: int = 3) -> bool:
        """Flow to create a macro from the last N actions.

        This method analyzes the recent execution history, proposes a new intelligent
        macro (plugin) using the MacroManager, and asks for user confirmation
        before saving it to the filesystem.

        Args:
            n (int): The number of recent actions to consider for the macro. Defaults to 3.

        Returns:
            bool: True if the macro was successfully created and saved, False otherwise.

        Raises:
            BusinessError: If there isn't enough history to form a macro.
        """
        logger.info(f"Initiating macro creation from last {n} actions.")
        recent_jsons = history_manager.get_recent_history_json(n)

        if not recent_jsons:
            self.automator.speak(
                "Não encontrei ações recentes suficientes para criar uma macro."
            )
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

    def _handle_explain_last_action(self):
        """Fetches the last successful action and asks LLM to explain it."""
        last_json = history_manager.get_last_successful_json()
        if not last_json:
            self.automator.speak("Não encontrei nenhuma ação recente para explicar.")
            return

        prompt = f"O usuário perguntou o que você acabou de fazer. Aqui está o JSON da sua última ação técnica: {last_json}\nExplique de forma curta, natural e humana o que você fez. Não explique o JSON, explique a ação."

        try:
            from core.ai.llm_agent import llm_agent

            explanation = llm_agent.generate_text(prompt)
            self.automator.speak(explanation)
        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            self.automator.speak("Tive um problema ao tentar gerar a explicação.")

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
                subprocess.run(
                    ["cmd", "/c", f"cd /d {target}"], shell=False, check=True
                )
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
                pyautogui.press("enter")
                return True
            return False
        except Exception as e:
            logger.error(f"Step execution error ({step.type.value}): {e}")
            return False

    def _check_authorization(self, action_config):
        risk_level = action_config.get("risk_level", "safe")
        intent = action_config.get("intent", action_config.get("action", "unknown"))

        if risk_level == "blocked":
            logger.warning("Blocked action detected!")
            self.automator.speak(
                "Atenção: Ação catastrófica detectada. Comando bloqueado por segurança."
            )
            history_manager.log_execution(
                self.last_input_text,
                self.last_input_source,
                intent,
                risk_level,
                "blocked",
                confidence=self.last_confidence,
                error_msg="Policy Blocked",
            )
            return False

        if risk_level == "dangerous":
            logger.warning("Dangerous action detected! Requesting authorization...")
            state_manager.set_state(
                JarvisState.CONFIRMING_DRY_RUN, context={"intent": intent}
            )

            self.automator.speak("Ação perigosa detectada. Deseja autorizar?")

            action_desc = action_config.get(
                "description",
                action_config.get(
                    "intent", action_config.get("action", "Ação do sistema")
                ),
            )
            self.active_dialog = SecurityDialog(action_desc)
            self.waiting_for_auth = True

            result = self.active_dialog.ask()

            self.waiting_for_auth = False
            self.active_dialog = None

            if not result:
                history_manager.log_execution(
                    self.last_input_text,
                    self.last_input_source,
                    intent,
                    risk_level,
                    "denied",
                    confidence=self.last_confidence,
                    error_msg="User Refused",
                )
            return result

        return True

    def handle(self, wakeword_name, confidence=1.0):
        logger.info(f"Dispatching action for: {wakeword_name}")
        self.last_confidence = confidence
        wakewords = self.config.get("wakewords", {})

        if wakeword_name not in wakewords:
            logger.error(f"No configuration found for wakeword: {wakeword_name}")
            self.automator.speak("Comando não configurado.")
            return

        action_config = wakewords[wakeword_name]

        if not self._check_authorization(action_config):
            return

        action_type = action_config.get("action")

        if action_type == "warp":
            self._handle_warp(action_config)
        elif action_type == "system":
            self._handle_system(action_config)
        elif action_type == "plugin":
            self._handle_plugin(action_config)
        else:
            logger.error(f"Unknown action: {action_type}")
            self.automator.speak("Tipo de ação desconhecida.")

    def handle_dynamic(self, action_config):
        """Legacy handler for non-ExecutionPlan actions. Chat responses are NOT logged as executable actions."""
        logger.info(f"Dispatching dynamic action: {action_config}")

        type_hint = action_config.get("type", "action")
        if type_hint == "chat":
            self.automator.speak(action_config.get("message", "Sem resposta."))
            # Chat is logged as context, but action_json (executable) is None
            history_manager.log_execution(
                self.last_input_text,
                self.last_input_source,
                "chat",
                "safe",
                "success",
                confidence=self.last_confidence,
            )
            return

        if not self._check_authorization(action_config):
            return

        action_type = action_config.get("action")
        if action_type == "warp":
            self._handle_warp(action_config)
        elif action_type == "system":
            self._handle_system(action_config)
        elif action_type == "plugin":
            self._handle_plugin(action_config)

    def _handle_warp(self, action_config):
        default_warp_path = (
            self.config.get("integrations", {})
            .get("warp", {})
            .get("path", self.automator.warp_path)
        )
        warp_path = action_config.get("warp_path", default_warp_path)
        commands = action_config.get("commands", [])

        steps = []
        steps.append(
            ExecutionStep(
                type=StepType.OPEN_APP,
                payload={"target": warp_path},
                description="Open Terminal",
            )
        )
        steps.append(
            ExecutionStep(
                type=StepType.WAIT,
                payload={"duration": 2.0},
                description="Wait for Terminal to load",
            )
        )
        steps.append(
            ExecutionStep(
                type=StepType.HOTKEY,
                payload={"keys": ["ctrl", "shift", "t"]},
                description="Open new tab",
            )
        )
        steps.append(
            ExecutionStep(
                type=StepType.WAIT,
                payload={"duration": 1.2},
                description="Wait for tab animation",
            )
        )

        for cmd in commands:
            steps.append(
                ExecutionStep(
                    type=StepType.TYPE_AND_ENTER,
                    payload={"text": cmd},
                    description=f"Run: {cmd}",
                )
            )
            steps.append(
                ExecutionStep(
                    type=StepType.WAIT,
                    payload={"duration": 0.5},
                    description="Wait for command",
                )
            )

        plan = ExecutionPlan(
            intent=action_config.get("intent", "warp_workflow"),
            explanation="Iniciando fluxo de trabalho no terminal",
            steps=steps,
            global_risk=RiskLevel.SAFE,
            schema_version="1.1",
        )
        self.execute_plan(plan)

    def _handle_system(self, action_config):
        commands = action_config.get("commands", [])
        risk_level_str = action_config.get("risk_level", "safe")
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.SAFE

        steps = [
            ExecutionStep(
                type=StepType.COMMAND,
                payload={"command": cmd},
                description=f"Execute: {cmd}",
            )
            for cmd in commands
        ]

        plan = ExecutionPlan(
            intent=action_config.get("intent", "system_cmd"),
            explanation="Executando comando de sistema",
            steps=steps,
            global_risk=risk_level,
            schema_version="1.1",
        )
        self.execute_plan(plan)

    def _handle_plugin(self, action_config):
        intent_name = action_config.get("intent")
        actions = plugin_manager.get_actions_for_intent(intent_name)
        if not actions:
            return

        steps = []
        for action in actions:
            a_type = action.get("type")
            if a_type == "system_open":
                steps.append(
                    ExecutionStep(
                        type=StepType.OPEN_APP, payload={"target": action.get("target")}
                    )
                )
            elif a_type == "wait":
                steps.append(
                    ExecutionStep(
                        type=StepType.WAIT,
                        payload={"duration": action.get("duration", 1.0)},
                    )
                )
            elif a_type == "keyboard_shortcut":
                steps.append(
                    ExecutionStep(
                        type=StepType.HOTKEY, payload={"keys": action.get("keys", [])}
                    )
                )
            elif a_type == "type_and_enter":
                steps.append(
                    ExecutionStep(
                        type=StepType.TYPE_AND_ENTER,
                        payload={"text": action.get("text", "")},
                    )
                )
            elif a_type == "system_exec":
                steps.append(
                    ExecutionStep(
                        type=StepType.COMMAND,
                        payload={"command": action.get("command", "")},
                    )
                )

        risk_level_str = action_config.get("risk_level", "safe")
        try:
            risk_level = RiskLevel(risk_level_str)
        except ValueError:
            risk_level = RiskLevel.SAFE

        plan = ExecutionPlan(
            intent=intent_name,
            explanation=f"Executando plugin: {intent_name}",
            steps=steps,
            global_risk=risk_level,
            schema_version="1.1",
        )
        self.execute_plan(plan)
