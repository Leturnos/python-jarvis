from pathlib import Path

import pytest

from core.security.path_guard import PathGuard
from core.shared.errors import SecurityError


def test_path_guard_allows_paths_within_workspace(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    sub_file = workspace / "src" / "main.py"
    sub_file.parent.mkdir(parents=True)
    sub_file.write_text("print('hello')", encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])

    validated = guard.validate_path(sub_file)
    assert validated == sub_file.resolve()
    assert guard.is_safe_path(sub_file) is True


def test_path_guard_resolves_relative_subpaths(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    # Relative to workspace
    validated = guard.validate_path("src/app.py", base_dir=workspace)
    assert validated == (workspace / "src" / "app.py").resolve()
    assert guard.is_safe_path("src/app.py", base_dir=workspace) is True


def test_path_guard_blocks_directory_traversal(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")

    guard = PathGuard(allowed_workspaces=[str(workspace)])

    traversal_path = workspace / ".." / "secret.txt"
    with pytest.raises(SecurityError) as exc_info:
        guard.validate_path(traversal_path)

    assert "not within any allowed workspace" in str(exc_info.value).lower()
    assert guard.is_safe_path(traversal_path) is False


def test_path_guard_blocks_system_directories(tmp_path: Path):
    workspace = tmp_path / "my_project"
    workspace.mkdir()
    guard = PathGuard(allowed_workspaces=[str(workspace)])

    system_paths = ["C:\\Windows\\System32", "C:\\Program Files", "/etc/passwd"]
    for p in system_paths:
        with pytest.raises(SecurityError):
            guard.validate_path(p)
        assert guard.is_safe_path(p) is False


def test_path_guard_defaults_to_project_root_when_empty():
    guard = PathGuard(allowed_workspaces=[])
    allowed = guard.get_allowed_workspaces()
    assert len(allowed) >= 1
    assert Path.cwd().resolve() in allowed
