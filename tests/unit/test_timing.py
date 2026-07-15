from core.shared.constants import Timing


def test_timing_load_and_reset():
    # Verify defaults are in place (or reset them to be sure)
    Timing.reset_defaults()

    original_short = Timing.UI_STABILIZATION_SHORT
    original_medium = Timing.UI_STABILIZATION_MEDIUM

    # Check original defaults match what is in _DEFAULTS
    assert original_short == Timing._DEFAULTS["UI_STABILIZATION_SHORT"]
    assert original_medium == Timing._DEFAULTS["UI_STABILIZATION_MEDIUM"]

    try:
        # 1. Verify we can load new values from config
        config = {
            "timing": {
                "ui_stabilization_short": 0.99,
                "ui_stabilization_medium": 0.88,
                "non_existent_constant": 123.45,  # should be ignored
            }
        }

        Timing.load_from_config(config)

        # Assert changes applied
        assert Timing.UI_STABILIZATION_SHORT == 0.99
        assert Timing.UI_STABILIZATION_MEDIUM == 0.88
        assert not hasattr(Timing, "NON_EXISTENT_CONSTANT")

        # 2. Reset defaults
        Timing.reset_defaults()

        # Assert values returned to default
        assert Timing.UI_STABILIZATION_SHORT == original_short
        assert Timing.UI_STABILIZATION_MEDIUM == original_medium

    finally:
        # Hard cleanup to prevent flaky test leakage
        Timing.reset_defaults()
