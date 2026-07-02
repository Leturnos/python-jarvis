from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

from core.shared.utils import (
    generate_icon_if_needed,
    get_resources_dir,
    is_autostart_enabled_check,
    manage_autostart,
    normalize_text,
    time_it,
)


def test_normalize_text():
    # Test lowercase
    assert normalize_text("HELLO") == "hello"
    # Test remove punctuation
    assert normalize_text("hello, world!") == "hello_world"
    # Test spaces to underscores
    assert normalize_text("hello   world") == "hello___world"
    # Test combinations
    assert normalize_text("  Hey, Jarvis!  ") == "hey_jarvis"


def test_time_it_success():
    mock_history = MagicMock()

    # NOTE: The import of history_manager is done locally and dynamically inside time_it()
    # (from core.persistence.history_db import history_manager). Consequently,
    # we must patch it directly at core.persistence.history_db.history_manager.
    with patch("core.persistence.history_db.history_manager", mock_history):

        @time_it
        def dummy_function(x, y):
            return x + y

        result = dummy_function(3, 4)
        assert result == 7
        mock_history.log_metric.assert_called_once()
        args, _ = mock_history.log_metric.call_args
        assert args[0] == "latency_dummy_function"
        assert isinstance(args[1], float)


def test_time_it_exception_handled():
    mock_history = MagicMock()
    mock_history.log_metric.side_effect = Exception("DB Error")

    # NOTE: The import of history_manager is done locally, so the patch is applied where
    # the object is originally defined/imported (core.persistence.history_db.history_manager).
    with (
        patch("core.persistence.history_db.history_manager", mock_history),
        patch("core.shared.utils.logger") as mock_logger,
    ):

        @time_it
        def dummy_function():
            return "ok"

        result = dummy_function()
        assert result == "ok"
        mock_logger.error.assert_called_once_with(
            "Failed to enqueue performance metric: DB Error"
        )


def test_get_resources_dir():
    # Robust test decoupled from implementation details (such as the number of chained .parent calls).
    # Since the get_resources_dir function is idempotent and safe (uses mkdir(exist_ok=True)), we can
    # test its actual properties directly on the local filesystem.
    res_dir = get_resources_dir()
    assert isinstance(res_dir, Path)
    assert res_dir.name == "resources"
    assert res_dir.exists()
    assert res_dir.is_dir()


def test_generate_icon_if_needed_exists():
    # Simplified to a single call and unified patch.
    with (
        patch("core.shared.utils.get_resources_dir") as mock_get_resources,
        patch("core.shared.utils.Image") as mock_image,
    ):
        mock_res_dir = MagicMock()
        mock_icon_path = MagicMock()
        mock_icon_path.exists.return_value = True
        mock_icon_path.__str__.return_value = "fake_icon.ico"
        mock_res_dir.__truediv__.return_value = mock_icon_path
        mock_get_resources.return_value = mock_res_dir

        res = generate_icon_if_needed()
        assert res == "fake_icon.ico"
        mock_image.new.assert_not_called()


def test_generate_icon_if_needed_not_exists():
    with (
        patch("core.shared.utils.get_resources_dir") as mock_get_resources,
        patch("core.shared.utils.Image") as mock_image,
        patch("core.shared.utils.ImageDraw"),
    ):
        mock_res_dir = MagicMock()
        mock_icon_path = MagicMock()
        mock_icon_path.exists.return_value = False
        mock_icon_path.__str__.return_value = "fake_icon.ico"
        mock_res_dir.__truediv__.return_value = mock_icon_path
        mock_get_resources.return_value = mock_res_dir

        mock_img_obj = MagicMock()
        mock_image.new.return_value = mock_img_obj

        res = generate_icon_if_needed()
        assert res == "fake_icon.ico"

        mock_image.new.assert_called_once_with("RGBA", (256, 256), (0, 0, 0, 0))
        mock_img_obj.save.assert_called_once()


@patch("core.shared.utils.winreg")
@patch("core.shared.utils.win32com.client.Dispatch")
@patch("core.shared.utils.get_resources_dir")
@patch("core.shared.utils.generate_icon_if_needed")
@patch("builtins.open", new_callable=mock_open)
def test_manage_autostart_enable(
    mock_file_open, mock_gen_icon, mock_get_resources, mock_dispatch, mock_winreg
):
    mock_gen_icon.return_value = "fake_icon.ico"

    mock_res_dir = MagicMock()
    mock_vbs_path = MagicMock()
    mock_vbs_path.exists.return_value = True
    mock_shortcut_path = MagicMock()
    mock_shortcut_path.__str__.return_value = "fake_shortcut.lnk"

    mock_res_dir.__truediv__.side_effect = lambda x: (
        mock_vbs_path if "vbs" in x else mock_shortcut_path
    )
    mock_get_resources.return_value = mock_res_dir

    mock_shell = MagicMock()
    mock_shortcut = MagicMock()
    mock_shell.CreateShortCut.return_value = mock_shortcut
    mock_dispatch.return_value = mock_shell

    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value = mock_key

    msg = manage_autostart(enable=True)

    assert "successfully added to Startup" in msg

    # 1. Verify if mock_dispatch was correctly initialized with WScript.Shell
    mock_dispatch.assert_called_once_with("WScript.Shell")

    # 2. Verify if the correct shortcut was created and saved
    mock_shell.CreateShortCut.assert_called_once_with("fake_shortcut.lnk")
    mock_shortcut.save.assert_called_once()

    # 3. Verify if the correct registry keys were set in the Windows Registry
    mock_winreg.SetValueEx.assert_called_once_with(
        mock_key, "JarvisAI", 0, mock_winreg.REG_SZ, '"fake_shortcut.lnk"'
    )
    mock_winreg.CloseKey.assert_called_once_with(mock_key)

    # 4. Verify the exact content written to launcher.vbs
    mock_file_open.assert_called_once()
    write_calls = mock_file_open().write.call_args_list
    assert len(write_calls) == 1
    written_content = write_calls[0][0][0]
    assert 'Set objShell = WScript.CreateObject("WScript.Shell")' in written_content
    assert "uv run main.py --hidden" in written_content


@patch("core.shared.utils.winreg")
@patch("core.shared.utils.get_resources_dir")
@patch("core.shared.utils.generate_icon_if_needed")
def test_manage_autostart_disable_success(
    mock_gen_icon, mock_get_resources, mock_winreg
):
    mock_gen_icon.return_value = "fake_icon.ico"
    mock_res_dir = MagicMock()

    mock_vbs_path = MagicMock()
    mock_vbs_path.exists.return_value = True
    mock_shortcut_path = MagicMock()
    mock_shortcut_path.__str__.return_value = "fake_shortcut.lnk"

    mock_res_dir.__truediv__.side_effect = lambda x: (
        mock_vbs_path if "vbs" in x else mock_shortcut_path
    )
    mock_get_resources.return_value = mock_res_dir

    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value = mock_key

    msg = manage_autostart(enable=False)

    assert "Jarvis removed from Startup" in msg
    mock_vbs_path.unlink.assert_called_once()
    mock_winreg.DeleteValue.assert_called_once_with(mock_key, "JarvisAI")
    mock_winreg.CloseKey.assert_called_once_with(mock_key)


@patch("core.shared.utils.winreg")
@patch("core.shared.utils.get_resources_dir")
@patch("core.shared.utils.generate_icon_if_needed")
def test_manage_autostart_disable_not_found(
    mock_gen_icon, mock_get_resources, mock_winreg
):
    mock_gen_icon.return_value = "fake_icon.ico"
    mock_res_dir = MagicMock()

    mock_vbs_path = MagicMock()
    mock_vbs_path.exists.return_value = False
    mock_shortcut_path = MagicMock()

    mock_res_dir.__truediv__.side_effect = lambda x: (
        mock_vbs_path if "vbs" in x else mock_shortcut_path
    )
    mock_get_resources.return_value = mock_res_dir

    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value = mock_key
    mock_winreg.DeleteValue.side_effect = FileNotFoundError()

    msg = manage_autostart(enable=False)

    assert "Jarvis was not in Startup" in msg
    mock_vbs_path.unlink.assert_not_called()
    mock_winreg.CloseKey.assert_called_once_with(mock_key)


@patch("core.shared.utils.winreg")
@patch("core.shared.utils.get_resources_dir")
@patch("core.shared.utils.generate_icon_if_needed")
def test_manage_autostart_exception(mock_gen_icon, mock_get_resources, mock_winreg):
    mock_winreg.OpenKey.side_effect = Exception("Registry failure")

    msg = manage_autostart(enable=True)
    assert "Error: Registry failure" in msg


@patch("core.shared.utils.winreg")
def test_is_autostart_enabled_check_true(mock_winreg):
    mock_key = MagicMock()
    mock_winreg.OpenKey.return_value = mock_key

    assert is_autostart_enabled_check() is True
    mock_winreg.OpenKey.assert_called_once()
    mock_winreg.QueryValueEx.assert_called_once_with(mock_key, "JarvisAI")
    mock_winreg.CloseKey.assert_called_once_with(mock_key)


@patch("core.shared.utils.winreg")
def test_is_autostart_enabled_check_false(mock_winreg):
    mock_winreg.OpenKey.side_effect = FileNotFoundError()
    assert is_autostart_enabled_check() is False


@patch("core.shared.utils.winreg")
def test_is_autostart_enabled_check_exception(mock_winreg):
    mock_winreg.OpenKey.side_effect = Exception("Registry error")
    assert is_autostart_enabled_check() is False
