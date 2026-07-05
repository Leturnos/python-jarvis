from unittest.mock import MagicMock

from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.step_executor import StepExecutor


def test_step_executor_wait():
    wm = MagicMock()
    spotify = MagicMock()
    tts = MagicMock()
    executor = StepExecutor({}, wm, spotify, tts)

    step = ExecutionStep(type=StepType.WAIT, payload={"duration": 0.01})
    assert executor.execute_step(step) is True
