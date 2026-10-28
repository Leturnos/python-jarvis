from pathlib import Path

from core.execution.execution_plan import RiskLevel
from core.security.path_guard import PathGuard
from core.tools.project_tool import ProjectInspectTool


def test_project_tool_metadata():
    tool = ProjectInspectTool()
    assert tool.name == "project_inspect"
    assert tool.risk_level == RiskLevel.SAFE
    schema = tool.get_parameters_schema()
    assert "action" in schema["properties"]


def test_project_tool_list_files(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    (workspace / "file1.py").write_text("a = 1", encoding="utf-8")
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "file2.py").write_text("b = 2", encoding="utf-8")

    # Ignored directory
    git_dir = workspace / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref", encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])
    tool = ProjectInspectTool(path_guard=guard)

    result = tool.execute(action="list_files", workspace=str(workspace), max_depth=2)
    assert result["success"] is True
    assert "file1.py" in result["tree"]
    assert "file2.py" in result["tree"]
    assert ".git" not in result["tree"]


def test_project_tool_read_file_snippet(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    target_file = workspace / "sample.py"
    target_file.write_text("print('hello world')\n", encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])
    tool = ProjectInspectTool(path_guard=guard)

    result = tool.execute(action="read_file", file_path=str(target_file))
    assert result["success"] is True
    assert "print('hello world')" in result["content"]


def test_project_tool_read_file_truncation(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    target_file = workspace / "large.txt"
    target_file.write_text("A" * 200, encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])
    tool = ProjectInspectTool(path_guard=guard)

    result = tool.execute(action="read_file", file_path=str(target_file), max_bytes=50)
    assert result["success"] is True
    assert result["truncated"] is True
    assert len(result["content"]) == 50


def test_project_tool_blocks_traversal_on_read(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    outside = tmp_path / "secret.env"
    outside.write_text("KEY=123", encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])
    tool = ProjectInspectTool(path_guard=guard)

    result = tool.execute(action="read_file", file_path=str(outside))
    assert result["success"] is False
    assert "allowed workspace" in result["error"].lower()


def test_project_tool_blocks_protected_files(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    env_file = workspace / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-test", encoding="utf-8")
    cfg_file = workspace / "config.yaml"
    cfg_file.write_text("dry_run: true", encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])
    tool = ProjectInspectTool(path_guard=guard)

    # Read .env blocked even if inside workspace
    res_env = tool.execute(action="read_file", file_path=str(env_file))
    assert res_env["success"] is False
    assert "protegido" in res_env["error"].lower()

    # Read config.yaml blocked
    res_cfg = tool.execute(action="read_file", file_path=str(cfg_file))
    assert res_cfg["success"] is False
    assert "protegido" in res_cfg["error"].lower()

    # List files hides protected files
    res_list = tool.execute(action="list_files", workspace=str(workspace))
    assert res_list["success"] is True
    assert ".env" not in res_list["tree"]
    assert "config.yaml" not in res_list["tree"]
