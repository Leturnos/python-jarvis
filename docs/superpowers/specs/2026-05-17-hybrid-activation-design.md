# Hybrid Activation System Design

## Overview
Implement a hybrid activation system for Jarvis, allowing the user to seamlessly switch between Wake Word detection, Push-To-Talk (PTT), and automatically suspending listening in specific contexts (like fullscreen applications).

## 1. Configuration Schema (`config.yaml`)

A new `voice_activation` block was added to support granular control over the activation gates.

```yaml
voice_activation:
  mode: "hybrid" # always_listening, push_to_talk, hybrid, disabled
  push_to_talk:
    key: "ctrl+alt"
    behavior: "hold" # hold or toggle
  wake_word:
    enabled: true
    keyword: "hey jarvis"
  auto_suspend:
    fullscreen: true
```

## 2. State Management Updates (`core/state.py`)

Two new states were added to improve observability and clarify lifecycles, separating concerns from the existing `MUTED` state.

*   `SLEEPING`: Deep sleep mode. Models are unloaded to save resources. Requires explicit wake up.
*   `SUSPENDED`: Contextual suspension (e.g., fullscreen app detected). Temporarily halts wake word evaluation but keeps models loaded for instant resume.
*   `MUTED`: Retained for manual, temporary user muting.

## 3. Activation Context & Manager (`core/activation.py`)

A new module isolates the decision-making logic from the main audio loop.

### ActivationContext
An object passed from the Controller to the Manager containing the environment snapshot:
```python
@dataclass
class ActivationContext:
    wakeword_score: float
    wakeword_detected: Optional[str]
    is_fullscreen: bool
    is_hotkey_pressed: bool
    current_state: JarvisState
    timestamp: float
```

### ActivationAction
A dataclass holding the decision and its source:
```python
@dataclass
class ActivationAction:
    action_type: ActivationActionType
    source: str # WAKE_WORD, PTT, FULLSCREEN_APP, MANUAL, NONE
```

### ActivationManager
The engine that evaluates the `ActivationContext` against the rules.

*   **Responsibilities:**
    *   Evaluate PTT key state (using `keyboard` library).
    *   Evaluate Fullscreen state (using `win32gui`).
    *   Apply Debounce/Hysteresis: Implement a `MIN_SUSPEND_DURATION` (2.0s) to prevent flickering.
    *   Metrics: Tracks counters for activations and suspensions.
*   **Output:** Returns an `ActivationAction` object.

## 4. Controller Integration (`core/controller.py`)

The main audio loop was refactored to delegate activation logic.

*   **Environment Polling:** Every tick in `IDLE`, the controller gathers the `ActivationContext`.
*   **Delegation:** `action = activation_manager.evaluate(context)`
*   **Execution:** 
    *   Handles `SUSPEND` by transitioning to `JarvisState.SUSPENDED`.
    *   Handles `TRIGGER_WAKE` and `TRIGGER_PTT_START` by transitioning to `JarvisState.LISTENING`.
    *   Handles `TRIGGER_PTT_STOP` (for hold behavior) by stopping recording immediately.
*   **Suspended State Handler:** A new `_handle_suspended` method polls for a `RESUME` action.

## 5. Security & Fallbacks
*   `keyboard` and `win32gui` calls are protected.
*   Fallback defaults are provided in `core/config.py` if `config.yaml` is missing the new block.
