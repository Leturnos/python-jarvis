# Design Specification: Jarvis UI/UX Refactoring and Modernization

**Date:** 2026-08-11  
**Status:** Approved  
**Scope:** Command Palette PySide6 Migration, Voice Overlay HUD Creation, and Multi-Tab Dashboard Expansion.

---

## 1. Overview and Objectives

The goal of this refactoring is to eliminate technical debt in the graphical user interface of the Jarvis project (removing the legacy Tkinter dependency from the Command Palette) and elevate the user experience (UX) to a premium level aligned with Windows 11 Fluent Design standards (via `PySide6` and `qfluentwidgets`).

### Core Goals:
1. **UI Unification:** Replace the Tkinter-based Command Palette with a native PySide6 implementation (`frameless QDialog`).
2. **Real-time Voice Feedback (Voice Overlay HUD):** Implement a transparent floating pill overlay (`VoiceOverlay`) centered at the bottom of the screen, displaying real-time voice states (listening, transcription, and assistant response).
3. **Comprehensive Dashboard (MainWindow):** Expand the main window to include navigation tabs (`Status`, `Execution History`, and `AI/Voice Settings`).

---

## 2. UI Architecture and Modules

### 2.1 Directory Structure

```
core/ui/
├── adapter.py              # Qt Signal adapter and backend bridge
├── app_controller.py       # Qt lifecycle controller, System Tray, and windows manager
├── command_palette_qt.py   # New native PySide6 Command Palette (replaces command_palette.py)
├── main_window.py          # Dashboard with NavigationView and tab support
├── security_ui.py          # Security authorization modal (existing)
├── voice_overlay.py        # New floating HUD pill overlay
├── widgets/
│   ├── status_card.py      # Extended status card
│   └── audio_visualizer.py  # Mini animated audio bar/wave widget
└── tabs/
    ├── status_tab.py       # Real-time status and microphone/wake word monitoring
    ├── history_tab.py      # Execution history tab reading from SQLite
    └── settings_tab.py     # Configuration tab for LLM providers, API keys, and voice thresholds
```

---

## 3. Detailed Component Specification

### 3.1 Native Command Palette (`core/ui/command_palette_qt.py`)
- **Type:** Frameless `QDialog` (`Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool`).
- **Global Hotkey:** `Ctrl + Alt + P` (via `keyboard` / native `win32gui`).
- **Visual Style:** Dark Fluent background (#1f1f1f / #2d2d2d), rounded corners, smooth padding, and subtle outer drop shadow.
- **Sub-components:**
  - `SearchLineEdit`: Auto-focused search input box.
  - Styled `QListWidget`: Filterable list displaying recent command execution history (from SQLite `history_manager`) and active plugin intents.
- **Behavior:** Automatic dismissal on `<Escape>`, focus loss (`FocusOut`), or item selection (`Enter` / double-click).

### 3.2 Voice Overlay HUD (`core/ui/voice_overlay.py`)
- **Type:** Floating frameless `QWidget` (`Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool`).
- **Screen Position:** Bottom-center of the primary monitor (just above the Windows taskbar).
- **Pill Elements:**
  - Animated state indicator (microphone icon / dynamic audio level wave).
  - Status/Transcription Label: Displays "Listening...", real-time STT text, or short AI responses.
- **Behavior:**
  - Automatically pops up when transitioning to `LISTENING`, `THINKING`, or `EXECUTING` states.
  - Auto-hides via a 3-second `QTimer` after returning to the `IDLE` state.

### 3.3 Multi-Tab Dashboard (`core/ui/main_window.py` & `core/ui/tabs/`)
`MainWindow` will be restructured using a Fluent `NavigationView` or `Pivot` from `qfluentwidgets`.

1. **Status Tab (`status_tab.py`):**
   - Integrates `StatusCardWidget` with live microphone volume meters, wake word score metrics, and active LLM provider info.
   - Quick action controls: Mute, Sleep, and Wake triggers.
2. **History Tab (`history_tab.py`):**
   - Interactive table/list consuming data from `history_manager` (SQLite).
   - Columns: Timestamp, Command/Transcription, Source (Voice/Palette), Execution Status (Success/Error), Risk Level.
   - Search bar and clear history action.
3. **Settings Tab (`settings_tab.py`):**
   - ComboBox for selecting active LLM Provider (Gemini, OpenAI, Anthropic, DeepSeek, OpenRouter).
   - API Key connection test with inline visual feedback.
   - Sliders and pickers for voice sensitivity (Wake Word Threshold, Push-to-Talk hotkey).

---

## 4. Threading & Qt Signals Integration

- All heavy processing (audio capture, STT, LLM streaming) remains isolated in existing worker threads (`command_worker`).
- GUI updates are strictly event-driven via Qt signals emitted by `JarvisUIAdapter`:
  - `visual_state_updated(dict)`: Concurrently updates `VoiceOverlay` and `StatusTab` on the Qt main thread without GUI freezing.

---

## 5. Implementation & Verification Plan

1. **Step 1:** Develop `core/ui/command_palette_qt.py` and remove Tkinter dependencies from `core/ui/command_palette.py`.
2. **Step 2:** Develop `core/ui/voice_overlay.py` and connect to `JarvisUIAdapter`.
3. **Step 3:** Restructure `core/ui/main_window.py` and build `status_tab.py`, `history_tab.py`, and `settings_tab.py`.
4. **Step 4:** Run test suite with `uv run pytest` and verify runtime behavior.
