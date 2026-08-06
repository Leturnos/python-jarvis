from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.plan_builder import is_action_trusted


def test_is_action_trusted_requires_full_path_match_and_system_open_action():
    config = {
        "security": {
            "trusted_apps": [
                {
                    "path": r"C:\Program Files\Spotify\Spotify.exe",
                    "allowed_actions": ["system_open"],
                }
            ]
        }
    }

    # Matching path and allowed action -> True
    trusted_step = ExecutionStep(
        type=StepType.OPEN_APP,
        payload={"target": r"C:\Program Files\Spotify\Spotify.exe"},
    )
    assert is_action_trusted(trusted_step, config) is True

    # Same app, but unallowed step type -> False
    untrusted_step = ExecutionStep(
        type=StepType.TYPE_AND_ENTER,
        payload={"target": r"C:\Program Files\Spotify\Spotify.exe", "text": "rm -rf /"},
    )
    assert is_action_trusted(untrusted_step, config) is False

    # Basename match only (different path) -> False
    fake_path_step = ExecutionStep(
        type=StepType.OPEN_APP,
        payload={"target": r"C:\Users\Fake\Downloads\Spotify.exe"},
    )
    assert is_action_trusted(fake_path_step, config) is False
