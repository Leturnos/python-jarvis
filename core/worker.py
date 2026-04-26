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
from core.state import state_manager, JarvisState
from core.job_queue import Job, JobType, JobStatus, job_manager
from core.execution_plan import ExecutionPlan

def _handle_llm(job: Job, dispatcher, notifier) -> bool:
    """
    Handles LLM-based dynamic commands.
    Extracts text via STT, matches against plugins, or falls back to LLM.
    """
    audio_bytes = job.payload
    notifier.notify("Jarvis", "Processando áudio...")
    
    # Check for silence to prevent Whisper from hanging
    pcm = np.frombuffer(audio_bytes, dtype=np.int16)
    if len(pcm) == 0 or np.max(np.abs(pcm)) < 50:
        logger.warning("Áudio silencioso detectado. Pulando STT para evitar travamento.")
        dispatcher.automator.speak("Desculpe, não ouvi nada.")
        return True
    
    # 1. STT
    text = stt_engine.transcribe(audio_bytes)
    if not text:
        dispatcher.automator.speak("Desculpe, não entendi.")
        return True # Considered final for this audio
        
    notifier.notify("Jarvis", f"Entendi: '{text}'.")
    
    # 2. Preparation
    intents = plugin_manager.get_intents()
    
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
        dispatcher.handle_dynamic(action_config)
        return True
    
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
        dispatcher.handle_dynamic(action_config)
        return True

    # 5. Stage 3: LLM Fallback (Gemini)
    notifier.notify("Jarvis", "Pensando...")
    dispatcher.last_confidence = 1.0
    action_json = llm_agent.process_instruction(text, context_commands=list(set(available_commands_map.values())))
    
    if not action_json:
        dispatcher.automator.speak("Erro ao processar instrução.")
        return False # Retryable if it's an LLM failure
        
    # 6. Dispatch via ExecutionPlan pipeline
    if action_json.get("type") == "chat":
        dispatcher.handle_dynamic(action_json)
    else:
        plan = ExecutionPlan.from_dict(action_json)
        dispatcher.handle_plan(plan)
    return True

def _handle_wakeword(job: Job, dispatcher, notifier) -> bool:
    """Handles wakeword detection events."""
    if isinstance(job.payload, (list, tuple)) and len(job.payload) == 2:
        wakeword_name, score = job.payload
    else:
        wakeword_name = "unknown"
        score = job.payload if isinstance(job.payload, (int, float)) else 0.0

    logger.info(f"Worker starting execution for '{wakeword_name}' (Score: {score:.2f})")
    notifier.notify("Jarvis", f"Comando '{wakeword_name}' detectado! (Score: {score:.2f})")
    dispatcher.handle(wakeword_name, confidence=score)
    return True

HANDLERS = {
    JobType.LLM_DYNAMIC: _handle_llm,
    JobType.WAKEWORD: _handle_wakeword
}

def command_worker(task_queue, dispatcher, notifier, stop_event, worker_busy):
    """Worker thread that executes commands from the queue using a dispatch table pattern."""
    pythoncom.CoInitialize()
    logger.info("Command worker thread initialized.")
    
    while not stop_event.is_set():
        try:
            job = task_queue.get(timeout=1.0)
            if not isinstance(job, Job):
                logger.warning(f"Received non-Job item in task_queue: {type(job)}. Ignoring.")
                task_queue.task_done()
                continue
        except queue.Empty:
            continue
            
        success = False
        try:
            worker_busy.set()
            state_manager.set_state(JarvisState.THINKING)
            job.status = JobStatus.RUNNING
            
            handler = HANDLERS.get(job.type)
            if not handler:
                logger.error(f"No handler found for job type: {job.type}")
                job.status = JobStatus.FAILED
                continue

            # Implement retry loop with exponential backoff
            while job.retries < job.max_retries and not success:
                try:
                    success = handler(job, dispatcher, notifier)
                    if success:
                        job.status = JobStatus.COMPLETED
                        job.finished_at = time.time()
                    else:
                        job.retries += 1
                        if job.retries < job.max_retries:
                            job.status = JobStatus.RETRYING
                            backoff_time = 2 ** job.retries
                            logger.info(f"Job {job.id} failed, retrying in {backoff_time}s...")
                            time.sleep(backoff_time)
                        else:
                            job.status = JobStatus.FAILED
                            job.finished_at = time.time()
                except Exception as e:
                    job.retries += 1
                    logger.error(f"Exception in job {job.id} (Attempt {job.retries}): {e}")
                    if job.retries < job.max_retries:
                        job.status = JobStatus.RETRYING
                        time.sleep(2 ** job.retries)
                    else:
                        job.status = JobStatus.FAILED
                        job.finished_at = time.time()
                        job.error = str(e)
            
        except Exception as e:
            logger.error(f"Critical error in command worker loop: {e}")
        finally:
            job_manager.add_job(job)
            task_queue.task_done()
            worker_busy.clear()
            state_manager.set_state(JarvisState.IDLE)
            logger.info(f"Worker finished job {job.id}, final status: {job.status.value}")

    pythoncom.CoUninitialize()
    logger.info("Command worker thread stopped.")
