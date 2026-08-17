from unittest.mock import patch

from core.infra.presets import PRESETS, detect_recommended_preset


def test_presets_structure():
    assert "ultra_economic" in PRESETS
    assert "economic" in PRESETS
    assert "balanced" in PRESETS
    assert "performance" in PRESETS

    for _name, preset in PRESETS.items():
        assert "stt" in preset
        assert "runtime" in preset
        assert "timing" in preset


def test_detect_preset_celeron_with_32gb_ram():
    # Celeron 2 cores with 32GB RAM -> CPU score 1, RAM score 4 -> min(1,4) = 1 (ultra_economic)
    with patch(
        "core.infra.presets.get_system_hardware_info",
        return_value={"cpu_cores": 2, "ram_gb": 32.0},
    ):
        assert detect_recommended_preset() == "ultra_economic"


def test_detect_preset_i7_with_8gb_ram():
    # 8 cores with 8GB RAM -> CPU score 3, RAM score 1 -> min(3,1) = 1 (ultra_economic)
    with patch(
        "core.infra.presets.get_system_hardware_info",
        return_value={"cpu_cores": 8, "ram_gb": 7.5},
    ):
        assert detect_recommended_preset() == "ultra_economic"


def test_detect_preset_balanced():
    # 6 cores with 16GB RAM -> CPU score 3, RAM score 3 -> min(3,3) = 3 (balanced)
    with patch(
        "core.infra.presets.get_system_hardware_info",
        return_value={"cpu_cores": 6, "ram_gb": 16.0},
    ):
        assert detect_recommended_preset() == "balanced"


def test_detect_preset_performance():
    # 12 cores with 32GB RAM -> CPU score 4, RAM score 4 -> min(4,4) = 4 (performance)
    with patch(
        "core.infra.presets.get_system_hardware_info",
        return_value={"cpu_cores": 12, "ram_gb": 32.0},
    ):
        assert detect_recommended_preset() == "performance"
