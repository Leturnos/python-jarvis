from pathlib import Path
from unittest.mock import MagicMock, patch

from core.execution.execution_plan import RiskLevel
from core.security.path_guard import PathGuard
from core.tools.git_tool import ScopedGitTool


def test_git_tool_metadata():
    tool = ScopedGitTool()
    assert tool.name == "git"
    assert tool.risk_level == RiskLevel.SAFE
    schema = tool.get_parameters_schema()
    assert "action" in schema["properties"]
    assert "workspace" in schema["properties"]


@patch("subprocess.run")
def test_git_status_success(mock_run, tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    mock_proc = MagicMock()
    mock_proc.stdout = "## main...origin/main\n M core/controller.py\n?? new_file.py\n"
    mock_run.return_value = mock_proc

    tool = ScopedGitTool(path_guard=guard)
    result = tool.execute(action="status", workspace=str(workspace))

    assert result["success"] is True
    assert result["action"] == "status"
    assert "M core/controller.py" in result["output"]
    mock_run.assert_called_once_with(
        ["git", "status", "--short", "--branch"],
        cwd=workspace.resolve(),
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    )


@patch("subprocess.run")
def test_git_diff_summary_truncates(mock_run, tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    # 10 lines of diff
    mock_proc = MagicMock()
    mock_proc.stdout = "\n".join(f"+ line {i}" for i in range(10))
    mock_run.return_value = mock_proc

    tool = ScopedGitTool(path_guard=guard)
    result = tool.execute(action="diff", workspace=str(workspace), max_lines=5)

    assert result["success"] is True
    assert result["truncated"] is True
    assert "line 4" in result["output"]
    assert "truncad" in result["output"].lower()


@patch("subprocess.run")
def test_git_commit_success(mock_run, tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    mock_proc = MagicMock()
    mock_proc.stdout = "[main 1234567] feat: test commit\n 1 file changed\n"
    mock_run.return_value = mock_proc

    tool = ScopedGitTool(path_guard=guard, allow_commit=True)
    result = tool.execute(
        action="commit", workspace=str(workspace), message="feat: test commit"
    )

    assert result["success"] is True
    assert "[main 1234567]" in result["output"]
    mock_run.assert_called_once_with(
        ["git", "commit", "-m", "feat: test commit"],
        cwd=workspace.resolve(),
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    )


def test_git_tool_blocks_unauthorized_workspace(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    tool = ScopedGitTool(path_guard=guard)
    result = tool.execute(action="status", workspace="C:\\Windows")

    assert result["success"] is False
    assert "allowed workspace" in result["error"].lower()


def test_git_commit_disallowed_when_config_false(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    tool = ScopedGitTool(path_guard=guard, allow_commit=False)
    result = tool.execute(
        action="commit", workspace=str(workspace), message="feat: disallowed"
    )

    assert result["success"] is False
    assert "not allowed" in result["error"].lower()
