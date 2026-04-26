import re
from core.logger_config import logger

class PromptGuard:
    """
    A security layer to detect and prevent Prompt Injection attacks and 
    ensure LLM outputs are structurally safe.
    """
    
    # Patterns that might indicate prompt injection attempts
    SUSPICIOUS_PATTERNS = [
        r"(?i)\bignore\b.*\b(previous|all)\b.*\binstructions\b",
        r"(?i)\bbypass\b.*\b(security|rules|instructions)\b",
        r"(?i)\bforget\b.*\b(previous|all)\b",
        r"(?i)\bdisregard\b",
        r"(?i)\bsystem\s+prompt\b",
        r"(?i)\byou\s+are\s+now\b",
        r"(?i)\bprint\b.*\b(instructions|rules)\b",
        r"(?i)\b(safe|dangerous|blocked)\b.*\brisk_level\b",
        r"(?i)\brm\s+-rf\b",
        r"(?i)\bdel\s+(/f|/s|/q)\b"
    ]
    
    @classmethod
    def is_input_safe(cls, user_text: str) -> bool:
        """
        Validates if the user input contains suspicious prompt injection patterns.
        Returns True if safe, False if suspicious.
        """
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, user_text):
                logger.warning(f"Prompt injection pattern detected in input: '{user_text}'")
                return False
        return True

    @classmethod
    def sanitize_output(cls, action_json: dict) -> dict:
        """
        Validates and sanitizes the LLM output to ensure it respects safety constraints.
        Supports both legacy format and new ExecutionPlan schema.
        """
        if not isinstance(action_json, dict):
            return action_json

        # 1. Handle new ExecutionPlan format (Steps)
        if "steps" in action_json:
            highest_risk = "safe"
            for step in action_json["steps"]:
                cmd = step.get("command", "").lower()
                target = step.get("target", "").lower()
                
                # Catastrophic blocks
                if any(bad in cmd for bad in ["rm -rf /", "del /f /s /q c:\\", "format c:"]) or \
                   any(bad in target for bad in ["windows", "system32"]):
                    logger.warning(f"Output sanitization: Blocked catastrophic step detected.")
                    step["step_risk"] = "blocked"
                
                # Escalation
                if step.get("step_risk") == "blocked":
                    highest_risk = "blocked"
                    break
            
            if highest_risk == "blocked":
                action_json["global_risk"] = "blocked"
            
            return action_json

        # 2. Legacy format handling
        risk_level = action_json.get("risk_level", "safe")
        action_type = action_json.get("action")
        
        if action_type in ["system", "warp"]:
            commands = action_json.get("commands", [])
            for cmd in commands:
                cmd_lower = cmd.lower()
                # Extremely dangerous commands should be blocked regardless of what the LLM says
                if any(bad in cmd_lower for bad in ["rm -rf /", "del /f /s /q c:\\", "format c:"]):
                    logger.warning(f"Output sanitization: Blocked catastrophic command: {cmd}")
                    action_json["risk_level"] = "blocked"
                    return action_json
                    
                # Other system commands should default to dangerous if not simple
                # This could be expanded with a whitelist
                
        return action_json
