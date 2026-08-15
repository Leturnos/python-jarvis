from unittest.mock import patch

from core.runtime.monitor import MemoryMonitor


def test_memory_monitor_triggers_trim():
    monitor = MemoryMonitor(interval_seconds=1, threshold_mb=100.0, enable_trim=True)
    with (
        patch("core.runtime.monitor.trim_working_set") as mock_trim,
        patch("core.runtime.monitor.gc.collect") as mock_gc,
    ):
        monitor._check_memory(force=True)
        assert mock_gc.called
        assert mock_trim.called


def test_memory_monitor_respects_trim_disabled():
    monitor = MemoryMonitor(interval_seconds=1, threshold_mb=100.0, enable_trim=False)
    with (
        patch("core.runtime.monitor.trim_working_set") as mock_trim,
        patch("core.runtime.monitor.gc.collect") as mock_gc,
    ):
        monitor._check_memory(force=True)
        assert mock_gc.called
        assert not mock_trim.called
