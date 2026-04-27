from dataclasses import dataclass
from typing import Optional, Dict, List
from difflib import SequenceMatcher
from core.utils import normalize_text
from core.plugin_manager import plugin_manager
from core.logger_config import logger

@dataclass
class ResolutionResult:
    intent_name: str
    confidence: float
    is_system: bool
    source: str
    matched_phrase: str

class CommandResolver:
    SYSTEM_ALIASES = {
        "replay": ["repetir", "repete", "repetir ultimo comando", "faz de novo", "de novo"],
        "create_macro": ["salvar como macro", "criar macro", "salve isso", "gravar sequencia"]
    }

    def __init__(self):
        pass

    def get_available_commands_map(self) -> Dict[str, str]:
        intents = plugin_manager.get_intents()
        available_commands_map = {}
        for i in intents:
            intent_name = i['intent']
            available_commands_map[normalize_text(intent_name)] = intent_name
            for phrase in i.get('phrases', []):
                available_commands_map[normalize_text(phrase)] = intent_name
        
        for intent, aliases in self.SYSTEM_ALIASES.items():
            for alias in aliases:
                available_commands_map[normalize_text(alias)] = intent
                
        return available_commands_map

    def get_available_intent_names(self) -> List[str]:
        return list(set(self.get_available_commands_map().values()))

    def resolve(self, text: str, threshold: float = 0.7) -> Optional[ResolutionResult]:
        available_commands_map = self.get_available_commands_map()
        available_commands = list(available_commands_map.keys())
        normalized = normalize_text(text)

        # Stage 1: Exact Match
        if normalized in available_commands:
            matched_intent = available_commands_map[normalized]
            is_system = matched_intent in self.SYSTEM_ALIASES
            logger.info(f"Exact match found: {normalized} -> {matched_intent}")
            return ResolutionResult(
                intent_name=matched_intent,
                confidence=1.0,
                is_system=is_system,
                source="voice_exact",
                matched_phrase=normalized
            )

        # Stage 2: Fuzzy Match
        best_match = None
        highest_ratio = 0.0
        for cmd in available_commands:
            ratio = SequenceMatcher(None, normalized, cmd).ratio()
            if ratio > highest_ratio:
                highest_ratio = ratio
                best_match = cmd
        
        if best_match and highest_ratio > threshold:
            matched_intent = available_commands_map[best_match]
            is_system = matched_intent in self.SYSTEM_ALIASES
            logger.info(f"Fuzzy match found: {best_match} for {normalized} (Score: {highest_ratio:.2f}) -> {matched_intent}")
            return ResolutionResult(
                intent_name=matched_intent,
                confidence=highest_ratio,
                is_system=is_system,
                source="voice_fuzzy",
                matched_phrase=best_match
            )

        return None
