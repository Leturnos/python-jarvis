from unittest.mock import MagicMock, patch

import numpy as np

from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.step_executor import StepExecutor
from core.media.models import AutoplayStrategy, MediaAction, MediaIntent, QueryType
from core.media.providers.spotify import SpotifyProvider
from core.media.spotify_automator import Box, SpotifyAutomator


def test_execution_step_spotify_click_play():
    # Test step deserialization with payload type check
    step_data = {
        "type": "spotify_click_play",
        "click_type": "playlist",
        "step_risk": "safe",
    }
    step = ExecutionStep.from_dict(step_data)
    assert step.type == StepType.SPOTIFY_CLICK_PLAY
    assert step.payload.get("click_type") == "playlist"

    # Test default click_type
    step_data_default = {"type": "spotify_click_play", "step_risk": "safe"}
    step_default = ExecutionStep.from_dict(step_data_default)
    assert step_default.payload.get("click_type") == "search"


def test_spotify_provider_resolve():
    # Mocking playlists load
    provider = SpotifyProvider(playlists_path="data/media/playlists.json")

    # Test Mood playlist mapping
    intent_playlist = MediaIntent(
        action=MediaAction.PLAY_QUERY, query="animada", query_type=QueryType.MOOD
    )
    with (
        patch.object(
            provider, "_load_intents", return_value={"animada": "spotify:playlist:123"}
        ),
        patch.object(provider.nlp, "score_query", return_value=("animada", 0.9)),
    ):
        plan = provider.resolve(intent_playlist)
        assert plan.strategy == AutoplayStrategy.MEDIA_KEY
        # Check that focus_window is added to steps
        has_focus = any(s.type == StepType.FOCUS_WINDOW for s in plan.steps)
        assert has_focus

    # Test Entity mapping
    intent_search = MediaIntent(
        action=MediaAction.PLAY_QUERY, query="Linkin Park", query_type=QueryType.ENTITY
    )
    plan_search = provider.resolve(intent_search)
    assert plan_search.strategy == AutoplayStrategy.TAB_ENTER
    has_focus = any(s.type == StepType.FOCUS_WINDOW for s in plan_search.steps)
    assert has_focus


def test_step_executor_executes_click_play_with_payload():
    automator = MagicMock()
    executor = StepExecutor(
        config={},
        window_manager=MagicMock(),
        spotify_automator=automator,
        tts_engine=MagicMock(),
    )

    step = ExecutionStep(
        type=StepType.SPOTIFY_CLICK_PLAY, payload={"click_type": "playlist"}
    )
    executor.execute_step(step)

    automator.spotify_click_play.assert_called_once_with(
        click_type="playlist", uri=None
    )


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_coordinates(
    mock_wm_class, mock_gw, mock_pyautogui
):
    # Mock WindowManager instance
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    # Mock window object
    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"

    # Mock gw and find_spotify_window
    mock_gw.getAllWindows.return_value = [mock_win]

    # Mock wm behavior
    mock_wm.find_processes.return_value = {1234}

    # Mock win32process to associate HWND with PID
    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        # Automator setup
        config = {"media": {"spotify": {"search_click_x": 900, "search_click_y": 450}}}
        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.return_value = None
        automator = SpotifyAutomator(
            config=config,
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)
        automator.is_spotify_playing = MagicMock(return_value=True)

        # Under test: playlist click (relative)
        res = automator.spotify_click_play(click_type="playlist")
        assert res
        # center_x = 100 + 500 = 600, click_y = 200 + height * 0.4 = 520
        mock_pyautogui.click.assert_called_with(600, 520)

        # Under test: search click (absolute coordinate configured)
        mock_pyautogui.click.reset_mock()
        res = automator.spotify_click_play(click_type="search")
        assert res
        # With absolute hover configuration, it should first click/hover at 900, 450,
        # then fallback to playlist search which clicks 10% higher 600, 520
        mock_pyautogui.click.assert_any_call(900, 450)
        mock_pyautogui.click.assert_any_call(600, 520)

        # Under test: search click fallback (no config coordinates)
        mock_pyautogui.click.reset_mock()
        automator.config = {}
        res = automator.spotify_click_play(click_type="search")
        assert res
        # fallback: hover click (left+220=320, top+165=365) and playlist fallback click (600, 520)
        mock_pyautogui.click.assert_any_call(320, 365)
        mock_pyautogui.click.assert_any_call(600, 520)


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_image_search(
    mock_wm_class, mock_gw, mock_pyautogui
):
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    # Mock window object
    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"
    mock_gw.getAllWindows.return_value = [mock_win]

    mock_wm.find_processes.return_value = {1234}

    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        # Mock locateOnScreen to return different boxes for search anchor and play button
        mock_anchor_box = MagicMock()
        mock_anchor_box.left = 300
        mock_anchor_box.top = 110
        mock_anchor_box.width = 160
        mock_anchor_box.height = 30

        mock_play_box = MagicMock()
        mock_play_box.left = 400
        mock_play_box.top = 350
        mock_play_box.width = 64
        mock_play_box.height = 64

        def mock_locate(img_path, **kwargs):
            if "spotify_search_anchor.png" in str(img_path):
                return mock_anchor_box
            elif "spotify_play_button.png" in str(img_path):
                return mock_play_box
            return None

        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.side_effect = mock_locate

        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)
        automator.is_spotify_playing = MagicMock(return_value=True)

        res = automator.spotify_click_play(click_type="search")
        assert res
        # hover position = anchor_x (300+80=380), anchor_y (125) + 10% window height (80) = 205
        mock_pyautogui.moveTo.assert_called_with(380, 205)
        # play button position = play_x (400+32=432), play_y (350+32=382)
        mock_pyautogui.click.assert_called_with(432, 382)


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_playlist_image_search(
    mock_wm_class, mock_gw, mock_pyautogui
):
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    # Mock window object
    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"
    mock_gw.getAllWindows.return_value = [mock_win]

    mock_wm.find_processes.return_value = {1234}

    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        # Mock locateOnScreen to return a Box-like mock for the play button
        mock_box = MagicMock()
        mock_box.left = 400
        mock_box.top = 350
        mock_box.width = 64
        mock_box.height = 64

        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.return_value = mock_box

        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)

        res = automator.spotify_click_play(click_type="playlist")
        assert res
        # click_x = left + w // 2 = 400 + 32 = 432
        # click_y = top + h // 2 = 350 + 32 = 382
        mock_pyautogui.click.assert_called_with(432, 382)

        # Verify it DID NOT send Tab or Enter
        for call_args in mock_pyautogui.press.call_args_list:
            assert call_args[0][0] not in ("tab", "enter")


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_search_chains_playlist(
    mock_wm_class, mock_gw, mock_pyautogui
):
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    # Mock window object
    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"
    mock_gw.getAllWindows.return_value = [mock_win]

    mock_wm.find_processes.return_value = {1234}

    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        # Mock locateOnScreen to return different boxes for search anchor and play button
        mock_anchor_box = MagicMock()
        mock_anchor_box.left = 300
        mock_anchor_box.top = 110
        mock_anchor_box.width = 160
        mock_anchor_box.height = 30

        mock_play_box = MagicMock()
        mock_play_box.left = 400
        mock_play_box.top = 350
        mock_play_box.width = 64
        mock_play_box.height = 64

        def mock_locate(img_path, **kwargs):
            if "spotify_search_anchor.png" in str(img_path):
                return mock_anchor_box
            elif "spotify_play_button.png" in str(img_path):
                return mock_play_box
            return None

        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.side_effect = mock_locate

        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)
        # Mock is_spotify_playing to return False so it chains
        automator.is_spotify_playing = MagicMock(return_value=False)

        res = automator.spotify_click_play(click_type="search")
        assert res

        # 1. Hover at 380, 205 (10% window height below anchor 380, 125)
        mock_pyautogui.moveTo.assert_any_call(380, 205)
        # 2. Click play button first (432, 382)
        mock_pyautogui.click.assert_any_call(432, 382)
        # 3. Playback fails, clicks hover position (380, 205)
        mock_pyautogui.click.assert_any_call(380, 205)
        # 4. Chains playlist autoplay which calls play button (432, 382) again
        mock_pyautogui.click.assert_any_call(432, 382)


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_collection_coordinates(
    mock_wm_class, mock_gw, mock_pyautogui
):
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    # Mock window object
    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"
    mock_gw.getAllWindows.return_value = [mock_win]

    mock_wm.find_processes.return_value = {1234}

    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.return_value = None
        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)

        res = automator.spotify_click_play(
            click_type="playlist", uri="spotify:user:spotify:collection"
        )
        assert res
        # click_x = left + w // 2 = 600
        # click_y = top + height * 0.4 = 200 + 320 = 520
        mock_pyautogui.click.assert_called_with(600, 520)


def test_automator_find_active_filter_pill():
    automator = SpotifyAutomator(
        config={},
        window_manager=MagicMock(),
        tts_engine=MagicMock(),
        cv_matcher=MagicMock(),
    )

    # Create synthetic dark image (height=400, width=800)
    img = np.zeros((400, 800, 3), dtype=np.uint8)
    # Draw white pill at x=120, y=75, w=60, h=32 (within top_bound=50..140)
    img[75:107, 120:180] = 255

    pill = automator.find_active_filter_pill(img)
    assert pill is not None
    assert pill.left == 120
    assert pill.top == 75
    assert pill.width == 60
    assert pill.height == 32

    # High-DPI test with scale_factor=1.25
    scale = 1.25
    img_dpi = np.zeros((500, 1000, 3), dtype=np.uint8)
    # 75 * 1.25 = ~93, 32 * 1.25 = 40, w = 75
    img_dpi[93:133, 150:225] = 255
    pill_dpi = automator.find_active_filter_pill(img_dpi, scale_factor=scale)
    assert pill_dpi is not None
    assert pill_dpi.left == 150

    # Small image (height smaller than top_bound) returns None gracefully without error
    small_img = np.zeros((30, 200, 3), dtype=np.uint8)
    assert automator.find_active_filter_pill(small_img) is None


def test_automator_wait_for_playback_polling():
    automator = SpotifyAutomator(
        config={},
        window_manager=MagicMock(),
        tts_engine=MagicMock(),
        cv_matcher=MagicMock(),
    )
    # Returns False on first 2 calls, True on 3rd
    automator.is_spotify_playing = MagicMock(side_effect=[False, False, True])
    with patch("time.sleep"):
        assert automator._wait_for_playback(max_attempts=3, interval=0.1) is True
    assert automator.is_spotify_playing.call_count == 3


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_active_pill(
    mock_wm_class, mock_gw, mock_pyautogui
):
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"
    mock_gw.getAllWindows.return_value = [mock_win]
    mock_wm.find_processes.return_value = {1234}

    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.return_value = None
        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)
        automator.is_spotify_playing = MagicMock(return_value=True)

        mock_pill = Box(left=120, top=75, width=60, height=32)
        mock_play = Box(left=400, top=150, width=48, height=48)

        # Initial fast-path returns None, after hover returns mock_play
        automator.find_spotify_green_button = MagicMock(side_effect=[None, mock_play])
        automator.find_active_filter_pill = MagicMock(return_value=mock_pill)

        res = automator.spotify_click_play(click_type="search")
        assert res

        # Expected hover: win.left + pill.left + 100 = 100 + 120 + 100 = 320
        # hover_y: win.top + pill.top + pill.height + 45 = 200 + 75 + 32 + 45 = 352
        mock_pyautogui.moveTo.assert_called_with(320, 352)

        # Expected click on revealed play button:
        # win.left + play.left + play.w//2 = 100 + 400 + 24 = 524
        # win.top + play.top + play.h//2 = 200 + 150 + 24 = 374
        mock_pyautogui.click.assert_called_with(524, 374)


@patch("core.media.spotify_automator.pyautogui")
@patch("core.media.spotify_automator.gw")
@patch("core.media.spotify_automator.WindowManager")
def test_automator_spotify_click_play_fast_path(mock_wm_class, mock_gw, mock_pyautogui):
    mock_wm = MagicMock()
    mock_wm_class.return_value = mock_wm

    mock_win = MagicMock()
    mock_win.left = 100
    mock_win.top = 200
    mock_win.width = 1000
    mock_win.height = 800
    mock_win.title = "Spotify Premium"
    mock_gw.getAllWindows.return_value = [mock_win]
    mock_wm.find_processes.return_value = {1234}

    with patch(
        "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
        return_value=(0, 1234),
    ):
        cv_matcher = MagicMock()
        cv_matcher.locate_template_multiscale.return_value = None
        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=cv_matcher,
        )
        automator.activate_spotify_window = MagicMock(return_value=True)
        automator.is_spotify_playing = MagicMock(return_value=True)

        mock_play = Box(left=450, top=170, width=48, height=48)
        automator.find_spotify_green_button = MagicMock(return_value=mock_play)

        res = automator.spotify_click_play(click_type="search")
        assert res

        # Fast path clicks immediately without needing moveTo hover:
        mock_pyautogui.moveTo.assert_not_called()
        mock_pyautogui.click.assert_called_once_with(100 + 450 + 24, 200 + 170 + 24)


def test_automator_dismiss_spotify_popup():
    automator = SpotifyAutomator(
        config={},
        window_manager=MagicMock(),
        tts_engine=MagicMock(),
        cv_matcher=MagicMock(),
    )

    # Synthetic image 800x600
    img = np.zeros((600, 800, 3), dtype=np.uint8)
    # Draw centered white CTA button: w=240, h=45 at x=280 (center 400), y=300
    img[300:345, 280:520] = 255

    coords = automator.dismiss_spotify_popup(img)
    assert coords is not None
    dismiss_x, dismiss_y = coords
    assert dismiss_x == 400
    # Expected dismiss_y: 300 + 45 + 35 = 380
    assert dismiss_y == 380


def test_window_manager_find_processes_matches_exe_suffix():
    from core.execution.window_manager import WindowManager

    wm = WindowManager()
    with patch("psutil.process_iter") as mock_iter:
        mock_proc1 = MagicMock()
        mock_proc1.info = {"pid": 9999, "name": "Spotify.exe", "exe": "C:\\Spotify.exe"}
        mock_iter.return_value = [mock_proc1]

        # Should match both 'spotify' and 'spotify.exe'
        pids1 = wm.find_processes(executable_name="spotify")
        assert 9999 in pids1

        pids2 = wm.find_processes(executable_name="spotify.exe")
        assert 9999 in pids2


def test_find_spotify_window_ignores_unrelated_process_with_spotify_in_title():
    from core.media.spotify_automator import SpotifyAutomator

    mock_wm = MagicMock()
    # Spotify runs on PID 5000
    mock_wm.find_processes.return_value = {5000}

    # Window 1: VS Code editing spotify_automator.py (PID 8888)
    vscode_win = MagicMock()
    vscode_win._hWnd = 1001
    vscode_win.title = "● spotify_automator.py - python-jarvis - Visual Studio Code"
    vscode_win.width = 1920
    vscode_win.height = 1080
    vscode_win.isMinimized = False

    # Window 2: Real Spotify (PID 5000)
    spotify_win = MagicMock()
    spotify_win._hWnd = 2002
    spotify_win.title = "Spotify Free"
    spotify_win.width = 1200
    spotify_win.height = 800
    spotify_win.isMinimized = False

    with (
        patch(
            "core.media.spotify_automator.gw.getAllWindows",
            return_value=[vscode_win, spotify_win],
        ),
        patch(
            "core.media.spotify_automator.win32process.GetWindowThreadProcessId",
            side_effect=lambda hwnd: (0, 8888) if hwnd == 1001 else (0, 5000),
        ),
    ):
        automator = SpotifyAutomator(
            config={},
            window_manager=mock_wm,
            tts_engine=MagicMock(),
            cv_matcher=MagicMock(),
        )

        matched = automator.find_spotify_window(timeout=0.1)
        assert matched is not None
        assert matched._hWnd == 2002
        assert matched.title == "Spotify Free"


def test_wait_for_window_ignores_unrelated_process_with_matching_title():
    from core.execution.window_manager import WindowManager

    wm = WindowManager()

    # EnumWindows callback mock testing:
    # If executable_name is "spotify.exe", a window from "Code.exe" must NOT match
    # even if title contains "spotify".
    with (
        patch(
            "core.execution.window_manager.win32gui.IsWindowVisible", return_value=True
        ),
        patch(
            "core.execution.window_manager.win32gui.GetWindowText",
            return_value="spotify_automator.py - VS Code",
        ),
        patch(
            "core.execution.window_manager.win32process.GetWindowThreadProcessId",
            return_value=(0, 8888),
        ),
        patch("core.execution.window_manager.psutil.Process") as mock_proc,
        patch("core.execution.window_manager.win32gui.EnumWindows") as mock_enum,
    ):
        proc_instance = MagicMock()
        proc_instance.name.return_value = "Code.exe"
        mock_proc.return_value = proc_instance

        def simulate_enum(callback, extra):
            callback(1001, extra)
            return True

        mock_enum.side_effect = simulate_enum

        matched = wm.wait_for_window(
            executable_name="spotify.exe", window_title_pattern="spotify", timeout=0.1
        )
        assert matched is None


def test_spotify_click_play_aborts_when_foreground_is_not_spotify():
    from core.execution.window_manager import WindowInfo
    from core.media.spotify_automator import SpotifyAutomator

    mock_wm = MagicMock()
    mock_wm.find_processes.return_value = {5000}

    # Foreground is VS Code (PID 8888)
    mock_wm.get_foreground_window_info.return_value = WindowInfo(
        hwnd=1001, pid=8888, executable="Code.exe", title="VS Code"
    )

    spotify_win = MagicMock()
    spotify_win._hWnd = 2002
    spotify_win.title = "Spotify Premium"
    spotify_win.width = 1200
    spotify_win.height = 800
    spotify_win.isMinimized = False

    automator = SpotifyAutomator(
        config={},
        window_manager=mock_wm,
        tts_engine=MagicMock(),
        cv_matcher=MagicMock(),
    )
    automator.find_spotify_window = MagicMock(return_value=spotify_win)
    automator.activate_spotify_window = MagicMock(return_value=True)

    # Should abort and return False without clicking
    res = automator.spotify_click_play(click_type="search")
    assert res is False
