# Jarvis LLM Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Integrate a local Speech-to-Text (STT) engine using Whisper and a Cloud LLM (Google Gemini) to process free-form voice commands dynamically.

**Architecture:** 
1. **Active Listening:** Extend `core/audio_engine.py` to record a continuous audio buffer after the wake word is detected, stopping upon a silence threshold.
2. **STT:** A new `core/stt_engine.py` will use `faster-whisper` directly to transcribe the recorded buffer locally.
3. **LLM Agent:** A new `core/llm_agent.py` will send the transcribed text to Google Gemini (via `google-generativeai`) using a strict JSON-schema prompt.
4. **Dynamic Dispatch:** Extend `core/dispatcher.py` to accept the JSON payload and execute it just like a static YAML action.

**Tech Stack:** Python 3.13, `openai-whisper`, `google-generativeai`, `SpeechRecognition` (optional/recording helper).

---

### Task 1: Environment & Dependencies Setup

**Files:**
- Modify: `pyproject.toml` (if using uv) or install via terminal.
- Modify: `.env` or `config.yaml` to include API keys.

- [x] **Step 1: Install new dependencies**
```bash
uv pip install openai-whisper SpeechRecognition google-generativeai soundfile
```

- [x] **Step 2: Add API Key Placeholder to Config**
Add `gemini_api_key: ""` to the `config.yaml` root level.

- [x] **Step 3: Update `core/config.py`**
Modify `core/config.py` to load `gemini_api_key` from YAML or environment variable (`os.getenv`).

- [x] **Step 4: Commit**
```bash
git add pyproject.toml uv.lock config.yaml core/config.py
git commit -m "chore(deps): add whisper, speechrecognition, and generativeai dependencies"
```

### Task 2: Active Listening Engine (Gravação Ativa)

**Files:**
- Modify: `core/audio_engine.py`

- [x] **Step 1: Implement `record_command_audio` in `core/audio_engine.py`**
Create a function that takes the PyAudio `stream`, reads frames continuously until the RMS energy drops below a silence threshold (e.g., 10) for 1.5 seconds or reaches 10 seconds maximum. It should return a raw audio buffer (bytes) or a numpy array.

```python
import time
import numpy as np

def record_command_audio(stream, max_seconds=10, silence_duration=1.5, silence_threshold=15.0):
    logger.info("Recording command...")
    frames = []
    start_time = time.time()
    silence_start = None
    
    while time.time() - start_time < max_seconds:
        try:
            data = stream.read(1280, exception_on_overflow=False)
            frames.append(data)
            pcm = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
            
            if rms < silence_threshold:
                if silence_start is None:
                    silence_start = time.time()
                elif time.time() - silence_start > silence_duration:
                    logger.info("Silence detected. Stopping recording.")
                    break
            else:
                silence_start = None
        except Exception as e:
            logger.error(f"Error recording audio: {e}")
            break
            
    return b"".join(frames)
```

- [x] **Step 2: Commit**
```bash
git add core/audio_engine.py
git commit -m "feat(audio): add continuous audio recording for commands"
```

### Task 3: STT Engine (Faster Whisper Local)

**Files:**
- Create: `core/stt_engine.py`

- [x] **Step 1: Implement `transcribe_audio`**
Create a Singleton or lazy-loaded instance of the Faster Whisper model (`tiny` or `base`) to transcribe the bytes.

```python
import whisper
import numpy as np
import io
import soundfile as sf
from core.logger_config import logger

class STTEngine:
    def __init__(self, model_size="tiny"):
        logger.info(f"Loading Whisper model ({model_size})...")
        # fp16=False for CPU compatibility by default
        self.model = whisper.load_model(model_size)
        
    def transcribe(self, audio_bytes, sample_rate=16000):
        try:
            # Convert raw bytes to numpy array
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            logger.info("Transcribing audio...")
            result = self.model.transcribe(audio_np, fp16=False, language="pt")
            text = result.get("text", "").strip()
            logger.info(f"Transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"STT Error: {e}")
            return ""

stt_engine = STTEngine("tiny")
```

- [x] **Step 2: Commit**
```bash
git add core/stt_engine.py
git commit -m "feat(stt): implement local whisper transcription engine"
```

### Task 4: LLM Agent (Gemini)

**Files:**
- Create: `core/llm_agent.py`

- [x] **Step 1: Implement `LLMAgent`**
Use `google.generativeai` to send the transcription and request JSON output.

```python
import json
import google.generativeai as genai
from core.logger_config import logger
from core.config import config

class LLMAgent:
    def __init__(self):
        api_key = config.get("gemini_api_key", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set.")
        genai.configure(api_key=api_key)
        # Using gemini-2.5-flash as it's the fast standard now
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        
    def process_instruction(self, text):
        prompt = f"""
        Você é o Jarvis, um assistente de terminal no Windows.
        O usuário falou: "{text}"
        Retorne um JSON estrito contendo a ação a ser executada.
        O formato deve ser OBRIGATORIAMENTE este:
        {{
            "action_type": "warp" ou "system",
            "commands": ["comando 1", "comando 2"],
            "warp_path": "C:\\Users\\Leandro\\AppData\\Local\\Programs\\Warp\\Warp.exe" (apenas se action_type for warp)
        }}
        Se a ação for de terminal (Warp), use comandos bash/powershell adequados (ex: npm start, cd path).
        Se a ação for de sistema, use comandos válidos de Windows CMD.
        Retorne APENAS o JSON, sem crases markdown (```json).
        """
        
        try:
            logger.info("Sending to Gemini...")
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            # Clean up markdown if Gemini ignores instructions
            if result.startswith("```json"):
                result = result[7:-3].strip()
            if result.startswith("```"):
                result = result[3:-3].strip()
                
            json_data = json.loads(result)
            logger.info(f"LLM Response: {json_data}")
            return json_data
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return None

llm_agent = LLMAgent()
```

- [x] **Step 2: Commit**
```bash
git add core/llm_agent.py
git commit -m "feat(llm): add Gemini AI agent for parsing natural language to JSON"
```

### Task 5: Dispatcher Refactor

**Files:**
- Modify: `core/dispatcher.py`

- [x] **Step 1: Add `handle_dynamic` method**
Add a method to execute the JSON object directly, bypassing the YAML lookup.

```python
    def handle_dynamic(self, action_config):
        """Executes a dynamically generated action dictionary from the LLM."""
        logger.info(f"Dispatching dynamic action: {action_config}")
        
        if not action_config or not isinstance(action_config, dict):
            logger.error("Invalid dynamic action config.")
            self.automator.speak("Não consegui processar a ação.")
            return
            
        action_type = action_config.get('action_type')
        
        if action_type == 'warp':
            self._handle_warp(action_config)
        elif action_type == 'system':
            self._handle_system(action_config)
        else:
            logger.error(f"Unknown action_type in dynamic config: {action_type}")
            self.automator.speak("Ação dinâmica desconhecida.")
```

- [x] **Step 2: Commit**
```bash
git add core/dispatcher.py
git commit -m "feat(core): extend ActionDispatcher to support dynamic JSON execution"
```

### Task 6: Main Loop Integration

**Files:**
- Modify: `main.py`

- [x] **Step 1: Wire it up in `command_worker` or the `main` loop**
When `hey_jarvis` is detected, stop feeding audio to openwakeword and start `record_command_audio`. Pass the buffer to STT, then to LLM, then to Dispatcher.
Wait, since `hey_jarvis` is a wakeword, we already have it in the main loop!
Modify the loop in `main.py`:
When `hey_jarvis` is detected:
1. `ui.update(status="Gravando...")`
2. `automator.speak("Sim?")`
3. Call `audio_bytes = record_command_audio(stream)` (Import it from `audio_engine`).
4. Pass the task to the queue as a tuple: `("llm_dynamic", audio_bytes)` instead of just `score`. 
   Wait, if it's `jarvis_fechar_tudo`, it should still route statically!
   So if `ww_name_clean == 'hey_jarvis'`:
     Do recording.
     Queue `('llm_dynamic', audio_bytes)`
   Else:
     Queue `(ww_name_clean, highest_score)`

Modify `command_worker` in `main.py` to handle the new task type:

```python
from core.stt_engine import stt_engine
from core.llm_agent import llm_agent

def command_worker(task_queue, dispatcher, notifier, stop_event):
    # ...
            task_type, payload = task_data
            
            if task_type == 'llm_dynamic':
                audio_bytes = payload
                notifier.notify("Jarvis", "Processando áudio...")
                
                # STT
                text = stt_engine.transcribe(audio_bytes)
                if not text:
                    dispatcher.automator.speak("Desculpe, não entendi.")
                    task_queue.task_done()
                    continue
                    
                notifier.notify("Jarvis", f"Entendi: '{text}'. Pensando...")
                
                # LLM
                action_json = llm_agent.process_instruction(text)
                if not action_json:
                    dispatcher.automator.speak("Erro ao processar instrução.")
                    task_queue.task_done()
                    continue
                    
                # Dispatch
                dispatcher.handle_dynamic(action_json)
                
            else:
                wakeword_name = task_type
                score = payload
                logger.info(f"Worker starting execution for '{wakeword_name}' (Score: {score:.2f})")
                notifier.notify("Jarvis", f"Comando '{wakeword_name}' detectado! (Score: {score:.2f})")
                dispatcher.handle(wakeword_name)
```

- [x] **Step 2: Commit**
```bash
git add main.py
git commit -m "feat(main): integrate active listening, STT, and LLM processing"
```
