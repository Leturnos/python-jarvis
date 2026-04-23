import time
import numpy as np
import queue
import pythoncom
from difflib import SequenceMatcher

from core.logger_config import logger
from core.stt_engine import stt_engine
from core.llm_agent import llm_agent
from core.utils import normalize_text
from core.plugin_manager import plugin_manager

def command_worker(task_queue, dispatcher, notifier, stop_event, worker_busy):
    """Worker thread that executes commands from the queue."""
    pythoncom.CoInitialize()
    logger.info("Command worker thread initialized.")
    
    while not stop_event.is_set():
        try:
            task_data = task_queue.get(timeout=1.0)
        except queue.Empty:
            continue
            
        try:
            task_type, payload = task_data
            
            if task_type == 'llm_dynamic':
                audio_bytes = payload
                notifier.notify("Jarvis", "Processando áudio...")
                
                # Check for silence to prevent Whisper from hanging
                pcm = np.frombuffer(audio_bytes, dtype=np.int16)
                if len(pcm) == 0 or np.max(np.abs(pcm)) < 50:
                    logger.warning("Áudio silencioso detectado. Pulando STT para evitar travamento.")
                    dispatcher.automator.speak("Desculpe, não ouvi nada.")
                    continue
                
                # 1. STT
                text = stt_engine.transcribe(audio_bytes)
                if not text:
                    dispatcher.automator.speak("Desculpe, não entendi.")
                    continue
                    
                notifier.notify("Jarvis", f"Entendi: '{text}'.")
                
                # 2. Preparation
                intents = plugin_manager.get_intents()
                
                # Build a mapping of possible phrases to their intent
                available_commands_map = {}
                for i in intents:
                    intent_name = i['intent']
                    available_commands_map[normalize_text(intent_name)] = intent_name
                    for phrase in i.get('phrases', []):
                        available_commands_map[normalize_text(phrase)] = intent_name
                
                available_commands = list(available_commands_map.keys())
                normalized = normalize_text(text)
                
                dispatcher.last_input_text = text
                dispatcher.last_input_source = "voice_llm"
                
                # 3. Stage 1: Exact Match
                if normalized in available_commands:
                    matched_intent = available_commands_map[normalized]
                    logger.info(f"Exact match found: {normalized} -> {matched_intent}")
                    dispatcher.last_input_source = "voice_exact"
                    dispatcher.last_confidence = 1.0
                    action_config = {
                        "action": "plugin",
                        "intent": matched_intent,
                        "risk_level": next((i['risk_level'] for i in intents if i['intent'] == matched_intent), "safe")
                    }
                    dispatcher._handle_plugin(action_config)
                    continue
                
                # 4. Stage 2: Fuzzy Match (difflib)
                best_match = None
                highest_ratio = 0.0
                for cmd in available_commands:
                    ratio = SequenceMatcher(None, normalized, cmd).ratio()
                    if ratio > highest_ratio:
                        highest_ratio = ratio
                        best_match = cmd
                
                if best_match and highest_ratio > 0.7:
                    matched_intent = available_commands_map[best_match]
                    logger.info(f"Fuzzy match found: {best_match} for {normalized} (Score: {highest_ratio:.2f}) -> {matched_intent}")
                    dispatcher.last_input_source = "voice_fuzzy"
                    dispatcher.last_confidence = highest_ratio
                    action_config = {
                        "action": "plugin",
                        "intent": matched_intent,
                        "risk_level": next((i['risk_level'] for i in intents if i['intent'] == matched_intent), "safe")
                    }
                    dispatcher._handle_plugin(action_config)
                    continue

                # 5. Stage 3: LLM Fallback (Gemini)
                notifier.notify("Jarvis", "Pensando...")
                dispatcher.last_confidence = 1.0 # Gemini confidence is opaque for now
                action_json = llm_agent.process_instruction(text, context_commands=list(set(available_commands_map.values())))
                
                if not action_json:
                    dispatcher.automator.speak("Erro ao processar instrução.")
                    continue
                    
                # 6. Dispatch
                dispatcher.handle_dynamic(action_json)
                
            else:
                wakeword_name = task_type
                score = payload
                logger.info(f"Worker starting execution for '{wakeword_name}' (Score: {score:.2f})")
                notifier.notify("Jarvis", f"Comando '{wakeword_name}' detectado! (Score: {score:.2f})")
                dispatcher.handle(wakeword_name, confidence=score)
            
        except Exception as e:
            logger.error(f"Error in command worker: {e}")
        finally:
            task_queue.task_done()
            worker_busy.clear()
            logger.info("Worker finished task and cleared busy flag.")

    pythoncom.CoUninitialize()
    logger.info("Command worker thread stopped.")