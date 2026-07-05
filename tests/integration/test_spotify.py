from unittest.mock import MagicMock, patch

from core.execution.execution_plan import ExecutionStep, StepType
from core.execution.step_executor import StepExecutor
from core.media.models import AutoplayStrategy, MediaAction, MediaIntent, QueryType
from core.media.providers.spotify import SpotifyProvider
from core.media.spotify_automator import SpotifyAutomator


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
        # fallback: hover click (350, 480) and playlist fallback click (600, 520)
        mock_pyautogui.click.assert_any_call(350, 480)
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
