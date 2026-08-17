import os
from typing import Any

import psutil

PRESETS: dict[str, dict[str, Any]] = {
    "ultra_economic": {
        "stt": {
            "model_size": "tiny",
            "compute_type": "int8",
            "auto_unload_seconds": 30,
            "lazy_load": True,
            "language": "pt",
            "device": "cpu",
            "max_prompt_chars": 150,
        },
        "runtime": {
            "memory_monitor": {
                "interval_seconds": 30,
                "threshold_mb": 350.0,
                "enable_working_set_trim": True,
            },
            "memory_optimization": {
                "lazy_load_secondary_modules": True,
                "unload_wakeword_on_suspend": True,
            },
        },
        "timing": {
            "ui_stabilization_short": 0.3,
            "ui_stabilization_medium": 0.5,
            "ui_stabilization_long": 1.0,
            "warp_startup_delay": 2.5,
            "warp_tab_creation": 1.5,
            "warp_cmd_execution": 0.8,
            "window_search_sleep": 0.3,
            "window_recovery_sleep": 0.5,
            "post_focus_render_sleep": 0.6,
            "autoplay_click_delay": 2.0,
            "mouse_detect_polling": 0.15,
        },
    },
    "economic": {
        "stt": {
            "model_size": "tiny",
            "compute_type": "int8",
            "auto_unload_seconds": 60,
            "lazy_load": True,
            "language": "pt",
            "device": "cpu",
            "max_prompt_chars": 150,
        },
        "runtime": {
            "memory_monitor": {
                "interval_seconds": 60,
                "threshold_mb": 500.0,
                "enable_working_set_trim": True,
            },
            "memory_optimization": {
                "lazy_load_secondary_modules": True,
                "unload_wakeword_on_suspend": True,
            },
        },
        "timing": {
            "ui_stabilization_short": 0.2,
            "ui_stabilization_medium": 0.4,
            "ui_stabilization_long": 0.7,
            "warp_startup_delay": 2.0,
            "warp_tab_creation": 1.2,
            "warp_cmd_execution": 0.6,
            "window_search_sleep": 0.2,
            "window_recovery_sleep": 0.4,
            "post_focus_render_sleep": 0.5,
            "autoplay_click_delay": 1.8,
            "mouse_detect_polling": 0.1,
        },
    },
    "balanced": {
        "stt": {
            "model_size": "tiny",
            "compute_type": "int8",
            "auto_unload_seconds": 180,
            "lazy_load": True,
            "language": "pt",
            "device": "cpu",
            "max_prompt_chars": 150,
        },
        "runtime": {
            "memory_monitor": {
                "interval_seconds": 60,
                "threshold_mb": 800.0,
                "enable_working_set_trim": True,
            },
            "memory_optimization": {
                "lazy_load_secondary_modules": True,
                "unload_wakeword_on_suspend": True,
            },
        },
        "timing": {
            "ui_stabilization_short": 0.1,
            "ui_stabilization_medium": 0.3,
            "ui_stabilization_long": 0.5,
            "warp_startup_delay": 2.0,
            "warp_tab_creation": 1.2,
            "warp_cmd_execution": 0.6,
            "window_search_sleep": 0.2,
            "window_recovery_sleep": 0.4,
            "post_focus_render_sleep": 0.5,
            "autoplay_click_delay": 1.8,
            "mouse_detect_polling": 0.1,
        },
    },
    "performance": {
        "stt": {
            "model_size": "base",
            "compute_type": "int8",
            "auto_unload_seconds": 0,
            "lazy_load": False,
            "language": "pt",
            "device": "cpu",
            "max_prompt_chars": 150,
        },
        "runtime": {
            "memory_monitor": {
                "interval_seconds": 120,
                "threshold_mb": 1500.0,
                "enable_working_set_trim": False,
            },
            "memory_optimization": {
                "lazy_load_secondary_modules": False,
                "unload_wakeword_on_suspend": False,
            },
        },
        "timing": {
            "ui_stabilization_short": 0.05,
            "ui_stabilization_medium": 0.15,
            "ui_stabilization_long": 0.3,
            "warp_startup_delay": 1.2,
            "warp_tab_creation": 0.8,
            "warp_cmd_execution": 0.3,
            "window_search_sleep": 0.1,
            "window_recovery_sleep": 0.2,
            "post_focus_render_sleep": 0.3,
            "autoplay_click_delay": 1.2,
            "mouse_detect_polling": 0.05,
        },
    },
}


def get_system_hardware_info() -> dict[str, Any]:
    """Retrieve total RAM (GB) and logical CPU cores count."""
    try:
        ram_gb = psutil.virtual_memory().total / (1024**3)
    except Exception:
        ram_gb = 8.0
    cpu_cores = os.cpu_count() or 2
    return {"ram_gb": ram_gb, "cpu_cores": cpu_cores}


def detect_recommended_preset() -> str:
    """Detect the recommended preset using the Bottleneck Principle min(CPU_Score, RAM_Score)."""
    hw = get_system_hardware_info()
    ram_gb = hw.get("ram_gb", 8.0)
    cpu_cores = hw.get("cpu_cores", 2)

    # 1. RAM Score
    if ram_gb < 8.0:
        ram_score = 1
    elif ram_gb <= 12.0:
        ram_score = 2
    elif ram_gb <= 24.0:
        ram_score = 3
    else:
        ram_score = 4

    # 2. CPU Score
    if cpu_cores <= 2:
        cpu_score = 1
    elif cpu_cores <= 4:
        cpu_score = 2
    elif cpu_cores <= 8:
        cpu_score = 3
    else:
        cpu_score = 4

    final_score = min(ram_score, cpu_score)
    score_map = {1: "ultra_economic", 2: "economic", 3: "balanced", 4: "performance"}
    return score_map.get(final_score, "balanced")
