import numpy as np
from PySide6.QtWidgets import QApplication

from core.audio.voice_catalog import (
    DEFAULT_STAGE_PHRASES,
    DEFAULT_VOICE_ID,
    STAGE_PHRASE_PRESETS,
    VOICE_CATALOG,
    get_voice_preset,
)
from core.audio.voice_dsp import (
    apply_friday_mk50_dsp,
    apply_jarvis_mk3_dsp,
    apply_voice_dsp,
)
from core.ui.tabs.settings_tab import SettingsTab


def test_voice_catalog_has_balanced_male_and_female_options_within_limit():
    assert 4 <= len(VOICE_CATALOG) <= 12

    genders = {preset.gender for preset in VOICE_CATALOG}
    assert "female" in genders
    assert "male" in genders

    ids = {preset.voice_id for preset in VOICE_CATALOG}
    assert DEFAULT_VOICE_ID in ids
    assert "jarvis_mk3" in ids
    assert "friday_mk50" in ids


def test_get_voice_preset_fallback():
    default_preset = get_voice_preset(None)
    assert default_preset.voice_id == DEFAULT_VOICE_ID

    unknown_preset = get_voice_preset("non_existent_voice")
    assert unknown_preset.voice_id == DEFAULT_VOICE_ID

    jarvis_preset = get_voice_preset("jarvis_mk3")
    assert jarvis_preset.dsp_profile == "jarvis_mk3"
    assert jarvis_preset.gender == "male"


def test_stage_phrase_presets_contain_all_four_lifecycle_stages():
    expected_keys = {
        "response_phrase",
        "completion_phrase",
        "no_speech_phrase",
        "not_understood_phrase",
    }
    assert set(DEFAULT_STAGE_PHRASES.keys()) == expected_keys
    for kit_name, kit_phrases in STAGE_PHRASE_PRESETS.items():
        assert set(kit_phrases.keys()) == expected_keys, f"Missing keys in {kit_name}"
        for val in kit_phrases.values():
            assert isinstance(val, str) and len(val.strip()) > 0


def test_apply_jarvis_and_friday_dsp_transform_and_bounds():
    sr = 22050
    t = np.linspace(0.0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
    raw = (
        0.5 * np.sin(2 * np.pi * 220.0 * t) + 0.3 * np.sin(2 * np.pi * 2800.0 * t)
    ).astype(np.float32)

    jarvis_out = apply_jarvis_mk3_dsp(raw, sr)
    friday_out = apply_friday_mk50_dsp(raw, sr)
    natural_out = apply_voice_dsp(raw, sr, "natural")

    assert jarvis_out.shape == raw.shape
    assert friday_out.shape == raw.shape
    assert jarvis_out.dtype == np.float32
    assert np.all(np.isfinite(jarvis_out))
    assert np.all(np.isfinite(friday_out))
    assert float(np.max(np.abs(jarvis_out))) <= 1.0
    assert float(np.max(np.abs(friday_out))) <= 1.0
    assert not np.allclose(jarvis_out, raw)
    assert np.allclose(natural_out, raw)


def test_apply_dsp_handles_empty_and_silent_buffers():
    empty = np.array([], dtype=np.float32)
    assert apply_jarvis_mk3_dsp(empty, 22050).size == 0

    silent = np.zeros(1024, dtype=np.float32)
    out = apply_jarvis_mk3_dsp(silent, 22050)
    assert out.shape == (1024,)
    assert float(np.max(np.abs(out))) == 0.0


def test_settings_tab_phrase_kits_and_voice_selector_ui():
    _app = QApplication.instance() or QApplication([])
    tab = SettingsTab()

    assert tab.voice_combo.count() == len(VOICE_CATALOG)

    tab._apply_phrase_kit("J.A.R.V.I.S.")
    assert tab.response_phrase_input.text() == "Às suas ordens, senhor."
    assert tab.completion_phrase_input.text() == "Concluído, senhor."
    assert tab.no_speech_phrase_input.text() == "Aguardando instruções, senhor."
    assert tab.not_understood_phrase_input.text() == "Poderia repetir, senhor?"

    tab._apply_phrase_kit("F.R.I.D.A.Y.")
    assert tab.response_phrase_input.text() == "Sim, chefe?"
    assert tab.completion_phrase_input.text() == "Feito, chefe."

    # Verify 2-column alignment format (Left Name \t Right Model Weight)
    for i in range(tab.voice_combo.count()):
        item_text = tab.voice_combo.itemText(i)
        assert "\t" in item_text, f"Missing 2-column tab separator in {item_text}"
        left_col, right_col = tab.voice_combo.split_columns(item_text)
        assert len(left_col) > 0
        assert "MB" in right_col

    # Verify bounded minimum width so long voice names never break card layout
    assert tab.voice_combo.minimumSizeHint().width() <= 200

    # Built-in voice has preview enabled; uninstalled voice has preview disabled until downloaded
    sapi_idx = tab.voice_ids.index("sapi5_default")
    tab.voice_combo.setCurrentIndex(sapi_idx)
    assert tab.voice_preview_btn.isEnabled() is True

    jarvis_idx = tab.voice_ids.index("jarvis_mk3")
    tab.voice_combo.setCurrentIndex(jarvis_idx)
    assert tab.voice_preview_btn.isEnabled() is tab.voice_mgr.is_voice_installed(
        "jarvis_mk3"
    )
    assert tab.voice_dl_status_lbl.wordWrap() is True
    assert tab.input_device_combo.maximumWidth() <= 380
