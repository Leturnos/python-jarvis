# Refatoração de Performance (Audio & STT) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implementar gravação de áudio não-bloqueante na thread principal e migrar para `faster-whisper` para otimização extrema.

**Architecture:** 
1. Limpeza de dependências (remoção de bibliotecas pesadas).
2. Migração da engine de Speech-to-Text de `openai-whisper` para `faster-whisper`.
3. Conversão do loop principal do `main.py` numa Máquina de Estados, eliminando a função síncrona `record_command_audio`.

**Tech Stack:** Python 3.13, `faster-whisper`, `uv`.

---

### Task 1: Limpeza de Dependências e Setup do `faster-whisper`

**Files:**
- Modify: `pyproject.toml`

- [x] **Step 1: Atualizar pacotes**

Use o terminal do Windows para remover o pesado `openai-whisper` e instalar o `faster-whisper`.
Como o `uv` é usado no projeto, precisamos ajustar as dependências explicitamente.
Run:
```bash
uv remove openai-whisper SpeechRecognition
uv remove torch torchvision torchaudio
uv add faster-whisper
```
*(Nota: Se `uv remove` falhar por não encontrar a dependência no pyproject.toml, ignore o erro e apenas garanta que `uv add faster-whisper` funcione e que o `pyproject.toml` não referencie o `openai-whisper` ou `torch`)*.

- [x] **Step 2: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: migrate from openai-whisper to faster-whisper for lighter footprint"
```

### Task 2: Refatoração do `core/stt_engine.py`

**Files:**
- Modify: `core/stt_engine.py`

- [x] **Step 1: Reescrever usando Faster Whisper**

Substitua todo o conteúdo de `core/stt_engine.py` pelo código abaixo, que utiliza a nova API do `faster-whisper`. A conversão de áudio para formato numpy ainda será suportada pelo motor do Faster Whisper, bastando passar o array ou um stream.
Note que o faster-whisper recebe o áudio diretamente como numpy array (normalizado ou não, dependendo da versão, mas a conversão padrão é dividir por 32768.0).

```python
import numpy as np
import io
from faster_whisper import WhisperModel
from core.logger_config import logger

class STTEngine:
    def __init__(self, model_size="tiny"):
        logger.info(f"Loading Faster Whisper model ({model_size}) on CPU...")
        # device="cpu", compute_type="int8" is the fastest configuration without GPU
        self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
    def transcribe(self, audio_bytes, sample_rate=16000):
        try:
            # Convert raw bytes to numpy float32 array normalized to [-1.0, 1.0]
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            logger.info("Transcribing audio with faster-whisper...")
            segments, info = self.model.transcribe(audio_np, beam_size=1, language="pt")
            
            text = " ".join([segment.text for segment in segments]).strip()
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
git commit -m "feat(stt): refactor engine to use faster-whisper on CPU"
```

### Task 3: Refatoração da Máquina de Estados no `main.py`

**Files:**
- Modify: `main.py`
- Modify: `core/audio_engine.py`

- [x] **Step 1: Remover o bloqueio antigo de `audio_engine.py`**

Remova a função `record_command_audio` de `core/audio_engine.py`, pois a gravação agora será tratada pelo estado no `main.py`. Mantenha apenas `get_audio_stream` e `load_wakeword_model`.

- [x] **Step 2: Modificar `main.py` para usar Máquina de Estados**

No `main.py`, defina as variáveis de estado antes do `try:`:
```python
    cooldown = 0
    # ... configurações de volume etc.
    was_busy = False

    # Novas variáveis de estado para gravação assíncrona
    is_recording_command = False
    command_frames = []
    silence_start = None
    command_start_time = None
```

Atualize o loop interno no `main.py` substituindo a chamada de `record_command_audio`.
Onde estava:
```python
                        if ww_name_clean == 'hey_jarvis':
                            ui.update(status="Gravando...")
                            automator.speak("Sim?")
                            audio_bytes = record_command_audio(stream)
                            task_queue.put(('llm_dynamic', audio_bytes))
```
Mude para configurar o estado inicial de gravação e NÃO enviar ainda pra fila:
```python
                        if ww_name_clean == 'hey_jarvis':
                            automator.speak("Sim?")
                            is_recording_command = True
                            command_frames = []
                            silence_start = None
                            command_start_time = time.time()
                            ui.update(status="Gravando...")
                            # Pula o processamento do restante neste ciclo
                            continue 
                        else:
                            worker_busy.set()
                            automator.speak("Sim?")
                            task_queue.put((ww_name_clean, highest_score))
```

E no início do loop (logo após ler os frames `pcm` do `stream.read()`), insira a lógica da máquina de estados para capturar o comando. Logo abaixo de `ui.update(volume=pcm):`:
```python
                    if is_recording_command:
                        ui.update(status="Gravando...")
                        command_frames.append(audio_data)
                        rms = np.sqrt(np.mean(pcm.astype(np.float32)**2))
                        
                        if rms < 15.0: # Silence threshold
                            if silence_start is None:
                                silence_start = time.time()
                            elif time.time() - silence_start > 1.5:
                                # Silence detected, end recording
                                is_recording_command = False
                                audio_bytes = b"".join(command_frames)
                                worker_busy.set()
                                task_queue.put(('llm_dynamic', audio_bytes))
                        else:
                            silence_start = None
                            
                        if time.time() - command_start_time > 10.0:
                            # Max timeout
                            is_recording_command = False
                            audio_bytes = b"".join(command_frames)
                            worker_busy.set()
                            task_queue.put(('llm_dynamic', audio_bytes))
                            
                        continue # Pula o processamento do openwakeword enquanto grava comando
```
*Note que ao fazer isso, você precisará remover a chamada antiga `worker_busy.set()` que ficava logo acima do `if ww_name_clean == 'hey_jarvis':`, movendo-a apenas para o bloco `else:` ou para o final da gravação do comando.*

Remova a importação `record_command_audio` no topo do arquivo.

- [x] **Step 3: Commit**

```bash
git add main.py core/audio_engine.py
git commit -m "feat(main): convert audio loop to non-blocking state machine"
```

---
**Nota Final para Revisão:** Após terminar as tasks, rode a aplicação localmente (`uv run main.py`), chame "Hey Jarvis" e observe como o terminal continuará fluido atualizando os medidores de volume durante a sua fala até que o sistema detecte o silêncio.