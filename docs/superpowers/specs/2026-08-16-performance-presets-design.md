# Performance Presets & Configuration Simplification Design Spec

**Date:** 2026-08-16  
**Status:** Approved  
**Target:** `python-jarvis`  

---

## 1. Overview & Goals

Currently, `config.yaml` exposes dozens of low-level parameters (STT model sizing, unload timers, memory ceilings, UI stabilization delays, wake word thresholds) that most users shouldn't manually tweak.

This design introduces a **4-tier Performance Preset System** (`ultra_economic`, `economic`, `balanced`, `performance`) plus an `auto` hardware-detection mode. 

### Key Objectives:
1. **Simplify `config.yaml`**: Reduce the default configuration file to high-level preferences (`performance_profile: "auto"`), while supporting transparent user overrides.
2. **Hardware Bottleneck Detection**: Automatically select the optimal preset based on the system's bottleneck (`min(CPU_Score, RAM_Score)`).
3. **Dashboard Settings Control**: Provide a 5-stop slider (`Auto`, `Ultra Econômico`, `Econômico`, `Equilibrado`, `Alto Desempenho`) in `SettingsTab` with a clear "Aplicar e Reiniciar Jarvis" workflow.

---

## 2. Architecture & Modules

### 2.1 `core/infra/presets.py`
A new dedicated module defining default configurations for each performance profile and the hardware detection logic.

#### Profile Parameters:
- **`ultra_economic`** (Ultra Econômico / PC Fraco/Notebook Antigo):
  - `stt`: `model_size: "tiny"`, `compute_type: "int8"`, `auto_unload_seconds: 30`, `lazy_load: true`
  - `runtime.memory_monitor`: `threshold_mb: 350.0`, `interval_seconds: 30`, `enable_working_set_trim: true`
  - `runtime.memory_optimization`: `unload_wakeword_on_suspend: true`
  - `timing`: `ui_stabilization_short: 0.3`, `ui_stabilization_medium: 0.5`, `ui_stabilization_long: 1.0`, `warp_startup_delay: 2.5`, `warp_tab_creation: 1.5`, `warp_cmd_execution: 0.8`

- **`economic`** (Econômico / PC Entrada):
  - `stt`: `model_size: "tiny"`, `compute_type: "int8"`, `auto_unload_seconds: 60`, `lazy_load: true`
  - `runtime.memory_monitor`: `threshold_mb: 500.0`, `interval_seconds: 60`, `enable_working_set_trim: true`
  - `timing`: `ui_stabilization_short: 0.2`, `ui_stabilization_medium: 0.4`, `ui_stabilization_long: 0.7`, `warp_startup_delay: 2.0`, `warp_tab_creation: 1.2`, `warp_cmd_execution: 0.6`

- **`balanced`** (Equilibrado / Padrão Recomendado):
  - `stt`: `model_size: "tiny"`, `compute_type: "int8"`, `auto_unload_seconds: 180`, `lazy_load: true`
  - `runtime.memory_monitor`: `threshold_mb: 800.0`, `interval_seconds: 60`, `enable_working_set_trim: true`
  - `timing`: `ui_stabilization_short: 0.1`, `ui_stabilization_medium: 0.3`, `ui_stabilization_long: 0.5`, `warp_startup_delay: 2.0`, `warp_tab_creation: 1.2`, `warp_cmd_execution: 0.6`

- **`performance`** (Alto Desempenho / PC Gamer/Workstation):
  - `stt`: `model_size: "base"`, `compute_type: "int8"`, `auto_unload_seconds: 0` (permanent warming in RAM), `lazy_load: false`
  - `runtime.memory_monitor`: `threshold_mb: 1500.0`, `interval_seconds: 120`, `enable_working_set_trim: false`
  - `timing`: `ui_stabilization_short: 0.05`, `ui_stabilization_medium: 0.15`, `ui_stabilization_long: 0.3`, `warp_startup_delay: 1.2`, `warp_tab_creation: 0.8`, `warp_cmd_execution: 0.3`

---

## 3. Bottleneck Hardware Detection Algorithm

Function `detect_recommended_preset()` in `core/infra/presets.py`:

```python
def detect_recommended_preset() -> str:
    # 1. Evaluate RAM Score
    total_ram_gb = get_total_ram_gb()
    if total_ram_gb < 8:
        ram_score = 1
    elif total_ram_gb <= 12:
        ram_score = 2
    elif total_ram_gb <= 24:
        ram_score = 3
    else:
        ram_score = 4

    # 2. Evaluate CPU Score
    cpu_cores = os.cpu_count() or 2
    if cpu_cores <= 2:
        cpu_score = 1
    elif cpu_cores <= 4:
        cpu_score = 2
    elif cpu_cores <= 8:
        cpu_score = 3
    else:
        cpu_score = 4

    # 3. Apply Bottleneck Principle
    final_score = min(ram_score, cpu_score)
    score_map = {1: "ultra_economic", 2: "economic", 3: "balanced", 4: "performance"}
    return score_map[final_score]
```

---

## 4. `config.yaml` Simplification & Configuration Resolution

### 4.1 Simplified `config.yaml`
The root `config.yaml` will be cleaned up to contain:
- `performance_profile: "auto"`
- Secrets, path configurations, custom integrations, wakewords, and explicit user overrides.

### 4.2 Configuration Loading Workflow (`core/infra/config.py`)
1. Read `config.yaml`.
2. Extract `performance_profile` (defaulting to `"auto"`).
3. If `"auto"`, call `detect_recommended_preset()` to determine the resolved profile.
4. Fetch `PRESETS[resolved_profile]`.
5. Perform a recursive deep merge: `config = deep_merge(preset_defaults, user_yaml_config)`.
6. Return `config` (retaining `_resolved_profile` in runtime metadata for UI display).

---

## 5. UI Integration (`SettingsTab` & System Restart)

### 5.1 `SettingsTab` Widget Components
- **Performance Profile Section**:
  - `QSlider` (5 stops: `0: Auto`, `1: Ultra Econômico`, `2: Econômico`, `3: Equilibrado`, `4: Alto Desempenho`).
  - `QLabel` displaying active profile details, e.g.:  
    `"Perfil Ativo: Auto (Detectado: Equilibrado - 8 Cores / 16GB RAM)"`
  - Explanatory description text updating based on the slider position.
- **Action Control**:
  - When the slider position changes, write `performance_profile` to `config.yaml`.
  - Display an **"Aplicar e Reiniciar Jarvis"** button.
  - Clicking the button emits a signal to `AppController` to safely restart the application process via `sys.executable` and `os.execv`.

---

## 6. Verification & Test Plan

1. **Unit Tests (`tests/test_presets.py`)**:
   - Verify `detect_recommended_preset()` under mocked RAM/CPU values (e.g. Celeron 2 cores + 32GB RAM yields `ultra_economic`).
   - Test recursive deep merge of preset defaults + user `config.yaml` overrides.
2. **Integration Tests (`tests/test_config.py`)**:
   - Verify loading `config.yaml` with `"auto"`, `"economic"`, `"performance"`, and custom overrides.
3. **UI & Verification**:
   - Test slider state persistence in `config.yaml`.
   - Run full test suite via `uv run pytest`.
