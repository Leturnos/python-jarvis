from core.execution.window_manager import WindowLayoutManager


def test_calculate_snap_bounds_left_half():
    manager = WindowLayoutManager()
    monitor_work_area = (0, 0, 1920, 1080)

    x, y, width, height = manager.calculate_snap_bounds(monitor_work_area, "snap_left")
    assert (x, y, width, height) == (0, 0, 960, 1080)


def test_calculate_snap_bounds_right_half():
    manager = WindowLayoutManager()
    monitor_work_area = (0, 0, 1920, 1080)

    x, y, width, height = manager.calculate_snap_bounds(monitor_work_area, "snap_right")
    assert (x, y, width, height) == (960, 0, 960, 1080)
