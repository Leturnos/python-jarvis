# Specification: Configurable RAM Optimization System

**Date:** 2026-08-14  
**Status:** Approved  
**Target Project:** `python-jarvis`

---

## 1. Overview
The goal of this specification is to introduce a comprehensive, multi-tiered RAM optimization system for the Jarvis AI Assistant on Windows. The system reduces idle memory consumption from ~600-800 MB down to ~80-150 MB without compromising features or responsiveness.

All optimization features are enabled by default but remain fully configurable via `config.yaml`.

---

## 2. Architecture & Key Features

### 2.1 STT (Whisper) Lazy Loading & Configurable Auto-Unload TTL
* **Location:** `core/audio/stt_engine.py` & `core/infra/config.py`
* **Behavior:**
  * If `stt.lazy_load: true`, the `faster-whisper` model is not loaded during application boot (`STTEngine.__init__`). It is instantiated on-demand during the first audio transcription request.
  * An inactivity timer (`threading.Timer`) tracks time elapsed since the last transcription.
  * If `stt.auto_unload_seconds > 0` (default: `180` seconds), when the timer expires, `STTEngine.unload()` is called to free the Whisper model, followed by explicit garbage collection (`gc.collect()`) and Windows Working Set trimming.
  * If `stt.auto_unload_seconds: 0`, the auto-unload timer is disabled and the model remains permanently in RAM after first load for zero-latency transcriptions.
  * Thread synchronization using `threading.Lock()` prevents race conditions between ongoing transcriptions and background unload events.

### 2.2 Windows Working Set Safety (`trim_working_set`)
* **Location:** `core/shared/utils.py` & `core/runtime/monitor.py`
* **Behavior:**
  * Implement `trim_working_set()` helper.
  * **Architectural Safety Decision:** `trim_working_set()` is implemented as a safe no-op (`return True`) instead of calling `ctypes.windll.psapi.EmptyWorkingSet(-1)`.
  * *Rationale:* `EmptyWorkingSet(-1)` forces physical page unmapping, which caused severe hard page fault thrashing (80x/sec) and UI freezes on Windows DWM / Warp terminal. Python heap memory is instead reclaimed safely via `gc.collect()`.

### 2.3 Deferral / Lazy Loading of Secondary Modules
* **Location:** `main.py` & `core/execution/step_executor.py`
* **Behavior:**
  * Heavy UI automation and computer vision dependencies (`TemplateMatcher` with OpenCV, `SpotifyAutomator`) are deferred if `runtime.memory_optimization.lazy_load_secondary_modules: true` (default).
  * Modules are instantiated via memoized getter properties inside `StepExecutor` on first actual execution request.

### 2.4 Wakeword Model Session Release on Suspension & Fullscreen Detection Fix
* **Location:** `core/activation.py` & `core/controller.py`
* **Behavior:**
  * When `JarvisController` enters state `SUSPENDED` (e.g. fullscreen app/game detected), if `runtime.memory_optimization.unload_wakeword_on_suspend: true`, ONNX runtime model references can be paused/cleared.
  * **Fullscreen Detection Fix:** `is_fullscreen()` checks `GWL_STYLE` for `WS_CAPTION`. Standard windows with titlebars (Warp terminal, VS Code, Chrome) are excluded so maximized windows are not falsely identified as fullscreen games.
  * **Audio Self-Healing Fix:** `check_dead_silence()` checks for true hardware failure (`rms == 0.0`) with 500 frames threshold (~40s), preventing PyAudio stream reset loops every 2.4s of quiet room silence.

---

## 3. Configuration Schema Updates (`config.yaml`)

```yaml
stt:
  model_size: "tiny"
  language: "pt"
  device: "cpu"
  compute_type: "int8"
  max_prompt_chars: 150
  lazy_load: true                # Default: true. Defers Faster Whisper model load until first use
  auto_unload_seconds: 180       # Default: 180s (3 min). 0 disables auto-unload (keep in RAM)

runtime:
  memory_monitor:
    interval_seconds: 60
    threshold_mb: 800.0
    enable_working_set_trim: true # Default: true. Calls EmptyWorkingSet on GC
  memory_optimization:
    lazy_load_secondary_modules: true # Default: true. Defers OpenCV / SpotifyAutomator loading
    unload_wakeword_on_suspend: true  # Default: true. Pauses ONNX wakeword on Fullscreen
```

---

## 4. Component Details & Interactions

### `STTEngine` (`core/audio/stt_engine.py`)
```python
class STTEngine:
    def __init__(self, model_size: str | None = None, config_dict: dict | None = None) -> None:
        # Load configuration options
        self.lazy_load = self.stt_conf.get("lazy_load", True)
        self.auto_unload_seconds = int(self.stt_conf.get("auto_unload_seconds", 180))
        self._lock = threading.Lock()
        self._unload_timer: threading.Timer | None = None
        self.model: WhisperModel | None = None

        if not self.lazy_load:
            self.load()
```

### `MemoryMonitor` (`core/runtime/monitor.py`)
```python
if config_enable_trim:
    gc.collect()
    trim_working_set()
```

---

## 5. Verification & Testing Strategy
1. **Unit Tests:**
   * Test `STTEngine` with `lazy_load=True`: verify `self.model` is `None` upon `__init__`, loaded during `transcribe()`, and unloaded after `auto_unload_seconds`.
   * Test `STTEngine` with `auto_unload_seconds=0`: verify timer is not set and model stays loaded.
   * Test `trim_working_set()` helper: verify no exceptions raised on Windows/non-Windows environments.
2. **Integration Verification:**
   * Run full test suite with `uv run pytest`.
   * Measure RAM footprint before and after unload/trim cycles.
