from typing import Any

from core.execution.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    RiskLevel,
    StepType,
)
from core.shared.constants import AppRegistry, Timing
from core.shared.errors import BusinessError


class PlanBuilder:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def build_warp_plan(self, action_config: dict[str, Any]) -> ExecutionPlan:
        warp_path = self.config.get("integrations", {}).get("warp", {}).get("path", "")
        if not warp_path or warp_path == "${WARP_PATH}":
            raise BusinessError(
                "Caminho do terminal Warp não está configurado. Verifique o arquivo config.yaml."
            )

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
                payload={"duration": Timing.WARP_STARTUP_DELAY},
                description="Wait for Terminal to load",
            )
        )
        steps.append(
            ExecutionStep(
                type=StepType.HOTKEY,
                payload={"keys": AppRegistry.WARP_NEW_TAB_SHORTCUT},
                description="Open new tab",
            )
        )
        steps.append(
            ExecutionStep(
                type=StepType.WAIT,
                payload={"duration": Timing.WARP_TAB_CREATION},
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
                    payload={"duration": Timing.WARP_CMD_EXECUTION},
                    description="Wait for command",
                )
            )

        return ExecutionPlan(
            intent=action_config.get("intent", "warp_workflow"),
            explanation="Iniciando fluxo de trabalho no terminal",
            steps=steps,
            global_risk=RiskLevel.SAFE,
            schema_version="1.1",
        )

    def build_system_plan(self, action_config: dict[str, Any]) -> ExecutionPlan:
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

        return ExecutionPlan(
            intent=action_config.get("intent", "system_cmd"),
            explanation="Executando comando de sistema",
            steps=steps,
            global_risk=risk_level,
            schema_version="1.1",
        )

    def build_plugin_plan(self, action_config: dict[str, Any]) -> ExecutionPlan:
        from core.plugins.plugin_manager import plugin_manager

        intent_name = action_config.get("intent")
        if not isinstance(intent_name, str):
            raise BusinessError("Plugin intent must be a string.")
        actions = plugin_manager.get_actions_for_intent(intent_name)
        if not actions:
            raise BusinessError(f"No actions found for plugin intent '{intent_name}'.")

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
            # execute system command step
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

        return ExecutionPlan(
            intent=intent_name,
            explanation=f"Executando plugin: {intent_name}",
            steps=steps,
            global_risk=risk_level,
            schema_version="1.1",
        )
