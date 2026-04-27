import time
import numpy as np
import queue
import pythoncom
import json
from difflib import SequenceMatcher

from core.logger_config import logger
from core.stt_engine import stt_engine
from core.llm_agent import llm_agent
from core.utils import normalize_text
from core.plugin_manager import plugin_manager
from core.state import state_manager, JarvisState
from core.job_queue import Job, JobType, JobStatus, job_manager
from core.execution_plan import ExecutionPlan
from core.command_resolver import CommandResolver
from core.errors import TechnicalError, BusinessError

# Singleton for the worker session
resolver = CommandResolver()

def _handle_llm(job: Job, dispatcher, notifier) -> bool:
    """
    Handles LLM-based dynamic commands with one-shot STT and CommandResolver.
    """
    # 1. Performance: One-shot STT (use cached text if retrying)
    if not job.payload_text:
        audio_bytes = job.payload
        notifier.notify("Jarvis", "Processando áudio...")
        
        pcm = np.frombuffer(audio_bytes, dtype=np.int16)
        if len(pcm) == 0 or np.max(np.abs(pcm)) < 50:
            logger.warning("Áudio silencioso detectado.")
            dispatcher.automator.speak("Desculpe, não ouvi nada.")
            return True # Final state for silence
            
        try:
            job.payload_text = stt_engine.transcribe(audio_bytes)
        except TechnicalError:
            raise # Let worker handle retry for STT failure
            
        if not job.payload_text:
            dispatcher.automator.speak("Desculpe, não entendi.")
            return True
            
        notifier.notify("Jarvis", f"Entendi: '{job.payload_text}'.")
        dispatcher.last_input_text = job.payload_text
        dispatcher.last_input_source = "voice_llm"

    # 2. Command Resolution (Separated Logic)
    result = resolver.resolve(job.payload_text)
    
    if result:
        dispatcher.last_input_source = result.source
        dispatcher.last_confidence = result.confidence
        
        if result.is_system:
            job_type = JobType.REPLAY if result.intent_name == "replay" else JobType.CREATE_MACRO
            new_job = Job(type=job_type, payload=job.payload)
            handler = HANDLERS[job_type]
            try:
                # System commands might raise BusinessError (e.g. Empty history)
                return handler(new_job, dispatcher, notifier)
            except BusinessError:
                raise # Propagate to prevent retry of LLM_DYNAMIC
        
        # Plugin action
        intents = plugin_manager.get_intents()
        action_config = {
            "action": "plugin",
            "intent": result.intent_name,
            "risk_level": next((i['risk_level'] for i in intents if i['intent'] == result.intent_name), "safe")
        }
        dispatcher.handle_dynamic(action_config)
        return True

    # 3. LLM Fallback (Technical Error aware)
    notifier.notify("Jarvis", "Pensando...")
    dispatcher.last_confidence = 1.0
    context_commands = resolver.get_available_intent_names()
    
    action_json = llm_agent.process_instruction(job.payload_text, context_commands=context_commands)
    if not action_json:
        # LLMAgent now raises TechnicalError on API failure
        raise TechnicalError("LLM processing failed")
        
    if action_json.get("type") == "chat":
        dispatcher.handle_dynamic(action_json)
    elif action_json.get("intent") in ["replay", "create_macro"]:
        matched_intent = action_json.get("intent")
        job_type = JobType.REPLAY if matched_intent == "replay" else JobType.CREATE_MACRO
        new_job = Job(type=job_type, payload=job.payload)
        handler = HANDLERS[job_type]
        try:
            # System commands might raise BusinessError (e.g. Empty history)
            return handler(new_job, dispatcher, notifier)
        except BusinessError:
            raise # Propagate to prevent retry of LLM_DYNAMIC
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

def _handle_replay(job: Job, dispatcher, notifier) -> bool:
    """Handles replay of the last successful command."""
    return dispatcher.replay_last_command()

def _handle_create_macro(job: Job, dispatcher, notifier) -> bool:
    """Initiates intelligent macro creation from history."""
    n = job.payload.get("n", 3) if isinstance(job.payload, dict) else 3
    return dispatcher.initiate_macro_creation(n=n)

HANDLERS = {
    JobType.LLM_DYNAMIC: _handle_llm,
    JobType.WAKEWORD: _handle_wakeword,
    JobType.REPLAY: _handle_replay,
    JobType.CREATE_MACRO: _handle_create_macro
}

def command_worker(task_queue, dispatcher, notifier, stop_event, worker_busy):
    """Worker thread that executes commands with separated Business/Technical errors."""
    pythoncom.CoInitialize()
    logger.info("Command worker thread initialized.")
    
    while not stop_event.is_set():
        try:
            job = task_queue.get(timeout=1.0)
            if not isinstance(job, Job):
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
                job.status = JobStatus.FAILED
                continue

            # Senior Retry Loop: Separates errors
            while job.retries < job.max_retries and not success:
                try:
                    success = handler(job, dispatcher, notifier)
                    if success:
                        job.status = JobStatus.COMPLETED
                        job.finished_at = time.time()
                    else:
                        # Logic returned False without raising (Legacy behavior)
                        job.status = JobStatus.FAILED
                        break
                        
                except BusinessError as be:
                    logger.warning(f"Business logic error in job {job.id}: {be}")
                    job.status = JobStatus.FAILED
                    job.error = str(be)
                    job.finished_at = time.time()
                    break # STOP immediately, do not retry business errors
                    
                except TechnicalError as te:
                    job.retries += 1
                    logger.error(f"Technical error in job {job.id} (Attempt {job.retries}): {te}")
                    if job.retries < job.max_retries:
                        job.status = JobStatus.RETRYING
                        backoff = 2 ** job.retries
                        time.sleep(backoff)
                    else:
                        job.status = JobStatus.FAILED
                        job.finished_at = time.time()
                        job.error = str(te)
                
                except Exception as e:
                    logger.error(f"Unexpected exception in job {job.id}: {e}")
                    job.status = JobStatus.FAILED
                    job.error = str(e)
                    break
            
        except Exception as e:
            logger.error(f"Critical worker loop crash: {e}")
        finally:
            job_manager.add_job(job)
            task_queue.task_done()
            worker_busy.clear()
            state_manager.set_state(JarvisState.IDLE)

    pythoncom.CoUninitialize()
