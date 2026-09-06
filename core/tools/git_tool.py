import subprocess
from pathlib import Path
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.security.path_guard import PathGuard
from core.shared.errors import SecurityError
from core.tools.base import BaseTool


class ScopedGitTool(BaseTool):
    """Scoped Git operations bound strictly to allowed workspaces."""

    name = "git"
    description = (
        "Executa inspeções controladas no Git (status, diff) e commits com mensagem "
        "convencional dentro de repositórios autorizados."
    )
    risk_level = RiskLevel.SAFE

    def __init__(
        self,
        path_guard: PathGuard | None = None,
        allow_commit: bool | None = None,
        max_diff_lines: int | None = None,
    ) -> None:
        self.guard = path_guard or PathGuard()
        git_cfg = config.get("tools", {}).get("developer", {}).get("git", {})
        self.allow_commit = (
            allow_commit
            if allow_commit is not None
            else git_cfg.get("allow_commit", True)
        )
        self.default_max_diff_lines = (
            max_diff_lines
            if max_diff_lines is not None
            else git_cfg.get("max_diff_lines", 300)
        )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "diff", "commit"],
                    "description": "Ação git a executar: 'status', 'diff' ou 'commit'.",
                },
                "workspace": {
                    "type": "string",
                    "description": "Caminho do repositório/workspace autorizado (ex: '.' ou caminho absoluto).",
                },
                "message": {
                    "type": "string",
                    "description": "Mensagem de commit (obrigatório se action='commit').",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Número máximo de linhas no diff (padrão: 300).",
                },
            },
            "required": ["action", "workspace"],
        }

    def execute(
        self,
        action: str = "status",
        workspace: str = ".",
        message: str = "",
        max_lines: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            resolved_ws = self.guard.validate_path(workspace)
        except SecurityError as e:
            return {"success": False, "error": str(e)}

        act = action.lower().strip()
        if act == "status":
            return self._git_status(resolved_ws)
        elif act == "diff":
            limit = max_lines if max_lines is not None else self.default_max_diff_lines
            return self._git_diff(resolved_ws, limit)
        elif act == "commit":
            return self._git_commit(resolved_ws, message)
        else:
            return {
                "success": False,
                "error": f"Unsupported git action '{action}'. Allowed: status, diff, commit.",
            }

    def _git_status(self, workspace: Path) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                ["git", "status", "--short", "--branch"],
                cwd=workspace,
                shell=False,
                capture_output=True,
                text=True,
                check=True,
            )
            return {
                "success": True,
                "action": "status",
                "workspace": str(workspace),
                "output": proc.stdout.strip(),
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "status", "error": err}

    def _git_diff(self, workspace: Path, max_lines: int) -> dict[str, Any]:
        try:
            # Try diff against HEAD first; fallback to unstaged diff
            cmd = ["git", "diff", "HEAD"]
            proc = subprocess.run(
                cmd,
                cwd=workspace,
                shell=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                proc = subprocess.run(
                    ["git", "diff"],
                    cwd=workspace,
                    shell=False,
                    capture_output=True,
                    text=True,
                    check=True,
                )

            lines = proc.stdout.splitlines()
            truncated = len(lines) > max_lines
            display_lines = lines[:max_lines]
            if truncated:
                display_lines.append(f"... [Diff truncado após {max_lines} linhas] ...")

            return {
                "success": True,
                "action": "diff",
                "workspace": str(workspace),
                "output": "\n".join(display_lines),
                "truncated": truncated,
                "total_lines": len(lines),
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "diff", "error": err}

    def _git_commit(self, workspace: Path, message: str) -> dict[str, Any]:
        if not self.allow_commit:
            return {
                "success": False,
                "action": "commit",
                "error": "Git commit is not allowed by configuration.",
            }

        msg = (message or "").strip()
        if not msg:
            return {
                "success": False,
                "action": "commit",
                "error": "Commit message cannot be empty.",
            }

        try:
            proc = subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=workspace,
                shell=False,
                capture_output=True,
                text=True,
                check=True,
            )
            return {
                "success": True,
                "action": "commit",
                "workspace": str(workspace),
                "output": proc.stdout.strip(),
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "commit", "error": err}
