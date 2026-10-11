from unittest.mock import patch

from core.audio.audio_cues import AudioCueManager, CueType


def test_play_cue_debounces_rapid_triggers():
    config = {"audio_cues": {"enabled": True, "debounce_ms": 200}}
    manager = AudioCueManager(config)

    with patch("core.audio.audio_cues._executor.submit") as mock_submit:
        # First call triggers sound
        assert manager.play_cue(CueType.WAKE) is True
        # Immediate second call within 200ms window gets debounced
        assert manager.play_cue(CueType.WAKE) is False
        mock_submit.assert_called_once()


def test_dispatcher_plays_action_completed_cue():
    from unittest.mock import MagicMock

    from core.execution.dispatcher import ActionDispatcher
    from core.execution.execution_plan import ExecutionPlan, RiskLevel

    mock_cue_manager = MagicMock()
    mock_step_executor = MagicMock()
    mock_step_executor.execute_step.return_value = True
    mock_tts = MagicMock()
    mock_plan_builder = MagicMock()

    dispatcher = ActionDispatcher(
        config={"dry_run": {"enabled": False}},
        step_executor=mock_step_executor,
        tts_engine=mock_tts,
        plan_builder=mock_plan_builder,
        audio_cue_manager=mock_cue_manager,
    )

    plan = ExecutionPlan(
        intent="test_action",
        explanation="Testing cue",
        global_risk=RiskLevel.SAFE,
        steps=[],
    )

    dispatcher.execute_plan(plan)
    mock_cue_manager.play_cue.assert_called_with(CueType.ACTION_COMPLETED)


def test_controller_plays_command_recognized_cue():
    from unittest.mock import MagicMock

    from core.controller import JarvisController

    mock_cue_manager = MagicMock()
    mock_task_queue = MagicMock()

    controller = JarvisController(
        config={"voice_activation": {"response_phrase": "Sim?"}},
        tts_engine=MagicMock(),
        dispatcher=MagicMock(),
        model=MagicMock(),
        loaded_names=["hey_jarvis"],
        ui=MagicMock(),
        tray=MagicMock(),
        task_queue=mock_task_queue,
        stop_event=MagicMock(),
        pa=MagicMock(),
        stream=MagicMock(),
        audio_cue_manager=mock_cue_manager,
    )
    controller.command_frames = [b"chunk1", b"chunk2"]

    controller._stop_listening_and_process(now=100.0)
    mock_cue_manager.play_cue.assert_called_with(CueType.COMMAND_RECOGNIZED)


def test_controller_plays_wake_cue():
    from unittest.mock import MagicMock

    import numpy as np

    from core.activation import (
        ActivationAction,
        ActivationActionType,
        ActivationContext,
    )
    from core.controller import JarvisController

    mock_cue_manager = MagicMock()
    mock_activation_manager = MagicMock()
    mock_action = ActivationAction(
        action_type=ActivationActionType.TRIGGER_WAKE,
        source="WAKE_WORD",
    )
    mock_activation_manager.evaluate.return_value = mock_action

    controller = JarvisController(
        config={
            "voice_activation": {
                "response_phrase": "Sim?",
                "thresholds": {"speech_rms": 10.0},
            }
        },
        tts_engine=MagicMock(),
        dispatcher=MagicMock(),
        model=MagicMock(),
        loaded_names=["hey_jarvis"],
        ui=MagicMock(),
        tray=MagicMock(),
        task_queue=MagicMock(),
        stop_event=MagicMock(),
        pa=MagicMock(),
        stream=MagicMock(),
        audio_cue_manager=mock_cue_manager,
    )
    controller.activation_manager = mock_activation_manager
    controller.cooldown = 0.0

    from core.runtime.state import JarvisState

    context = ActivationContext(
        wakeword_score=0.9,
        wakeword_detected="hey_jarvis",
        is_fullscreen=False,
        is_hotkey_pressed=False,
        current_state=JarvisState.IDLE,
        timestamp=10.0,
    )
    controller.model.predict.return_value = {"hey_jarvis": 0.9}

    controller._handle_idle(
        pcm=np.zeros(1280, dtype=np.int16), rms=50.0, context=context
    )
    mock_cue_manager.play_cue.assert_called_with(CueType.WAKE)
