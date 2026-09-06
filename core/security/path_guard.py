import os
from pathlib import Path

from core.infra.config import config
from core.infra.logger_config import logger
from core.shared.errors import SecurityError


class PathGuard:
    """Validates filesystem paths against configured workspace boundaries.

    Enforces the Principle of Least Privilege by neutralizing directory traversal
    (e.g., '../'), symlink redirections, and access to system-critical directories.
    """

    def __init__(self, allowed_workspaces: list[str | Path] | None = None) -> None:
        self._workspaces: list[Path] = []
        if allowed_workspaces is not None and len(allowed_workspaces) > 0:
            for ws in allowed_workspaces:
                self._add_workspace(ws)
        else:
            # Fallback to config or current working directory
            configured = (
                config.get("tools", {})
                .get("developer", {})
                .get("allowed_workspaces", [])
            )
            if configured:
                for ws in configured:
                    self._add_workspace(ws)
            else:
                self._workspaces.append(Path.cwd().resolve())

    def _add_workspace(self, workspace: str | Path) -> None:
        expanded = os.path.expandvars(str(workspace))
        p = Path(expanded).expanduser().resolve()
        if p not in self._workspaces:
            self._workspaces.append(p)

    def get_allowed_workspaces(self) -> list[Path]:
        """Returns the list of resolved, canonical allowed workspace paths."""
        return list(self._workspaces)

    def validate_path(
        self, path: str | Path, base_dir: str | Path | None = None
    ) -> Path:
        """Validates that a path is contained within at least one allowed workspace.

        Args:
            path: Target file or directory path (absolute or relative).
            base_dir: Optional base directory if path is relative.

        Returns:
            Resolved canonical Path.

        Raises:
            SecurityError: If path attempts traversal outside allowed workspaces.
        """
        raw_str = os.path.expandvars(str(path))
        raw_path = Path(raw_str).expanduser()

        if not raw_path.is_absolute():
            base = Path(base_dir).resolve() if base_dir else Path.cwd().resolve()
            candidate = (base / raw_path).resolve()
        else:
            candidate = raw_path.resolve()

        for ws in self._workspaces:
            try:
                if candidate.is_relative_to(ws):
                    return candidate
            except ValueError:
                continue

        logger.warning(
            f"PathGuard violation: '{path}' resolved to '{candidate}', "
            f"which is not within allowed workspaces: {[str(w) for w in self._workspaces]}"
        )
        raise SecurityError(f"Path '{path}' is not within any allowed workspace.")

    def is_safe_path(
        self, path: str | Path, base_dir: str | Path | None = None
    ) -> bool:
        """Checks if a path is safe and within allowed workspaces without raising an error."""
        try:
            self.validate_path(path, base_dir=base_dir)
            return True
        except SecurityError:
            return False
