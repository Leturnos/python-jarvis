from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from core.logger_config import logger

class StepType(Enum):
    COMMAND = "command"     # Terminal command
    OPEN_APP = "open_app"   # Start a file or app
    WRITE = "write"         # Type text
    NAVIGATE = "navigate"   # Change directory or focus
    WAIT = "wait"           # Delay

class RiskLevel(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"

@dataclass
class ExecutionStep:
    type: StepType
    payload: Dict[str, Any]
    step_risk: RiskLevel = RiskLevel.SAFE
    description: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionStep':
        # Explicit parser to prevent casting bugs
        s_type = data.get("type", "command")
        try:
            step_type = StepType(s_type)
        except ValueError:
            logger.warning(f"Unknown step type: {s_type}. Defaulting to COMMAND.")
            step_type = StepType.COMMAND
            
        risk_str = data.get("step_risk", "safe")
        try:
            risk = RiskLevel(risk_str)
        except ValueError:
            risk = RiskLevel.SAFE

        # Extract payload based on type
        payload = {}
        if step_type == StepType.COMMAND:
            payload["command"] = data.get("command", "")
        elif step_type == StepType.OPEN_APP:
            payload["target"] = data.get("target", "")
        elif step_type == StepType.WRITE:
            payload["text"] = data.get("text", "")
        elif step_type == StepType.NAVIGATE:
            payload["target"] = data.get("target", "")
        elif step_type == StepType.WAIT:
            payload["duration"] = data.get("duration", 1.0)

        return cls(
            type=step_type,
            payload=payload,
            step_risk=risk,
            description=data.get("description")
        )

@dataclass
class ExecutionPlan:
    intent: str
    explanation: str
    steps: List[ExecutionStep] = field(default_factory=list)
    global_risk: RiskLevel = RiskLevel.SAFE
    schema_version: str = "1.0"
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionPlan':
        steps_raw = data.get("steps", [])
        parsed_steps = [ExecutionStep.from_dict(s) for s in steps_raw]
        
        risk_str = data.get("global_risk", "safe")
        try:
            g_risk = RiskLevel(risk_str)
        except ValueError:
            g_risk = RiskLevel.SAFE
            
        # Ensure global risk is at least as high as the highest step risk
        for step in parsed_steps:
            if cls._compare_risk(step.step_risk, g_risk) > 0:
                g_risk = step.step_risk

        return cls(
            intent=data.get("intent", "unknown"),
            explanation=data.get("explanation", "No explanation provided."),
            steps=parsed_steps,
            global_risk=g_risk,
            schema_version=data.get("schema_version", "1.0")
        )

    @staticmethod
    def _compare_risk(r1: RiskLevel, r2: RiskLevel) -> int:
        levels = [RiskLevel.SAFE, RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.DANGEROUS, RiskLevel.BLOCKED]
        return levels.index(r1) - levels.index(r2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "intent": self.intent,
            "explanation": self.explanation,
            "global_risk": self.global_risk.value,
            "steps": [
                {
                    "type": s.type.value,
                    "step_risk": s.step_risk.value,
                    "description": s.description,
                    **s.payload
                } for s in self.steps
            ]
        }
