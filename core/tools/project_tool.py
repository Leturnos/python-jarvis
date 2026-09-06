from pathlib import Path
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.security.path_guard import PathGuard
from core.shared.errors import SecurityError
from core.tools.base import BaseTool


class ProjectInspectTool(BaseTool):
    """Safe project structure and code inspection tool constrained by PathGuard."""

    name = "project_inspect"
    description = (
        "Inspeciona a árvore de diretórios e lê trechos seguros de arquivos de código "
        "dentro dos repositórios autorizados."
    )
    risk_level = RiskLevel.SAFE

    IGNORED_DIRS = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "dist",
        "build",
    }

    def __init__(
        self,
        path_guard: PathGuard | None = None,
        max_file_size_kb: int | None = None,
    ) -> None:
        self.guard = path_guard or PathGuard()
        prj_cfg = config.get("tools", {}).get("developer", {}).get("project", {})
        self.default_max_bytes = (
            (max_file_size_kb * 1024)
            if max_file_size_kb is not None
            else (prj_cfg.get("max_file_size_kb", 50) * 1024)
        )

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list_files", "read_file"],
                    "description": "Ação a executar: 'list_files' ou 'read_file'.",
                },
                "workspace": {
                    "type": "string",
                    "description": "Caminho do repositório/workspace para listagem (padrão: '.').",
                },
                "file_path": {
                    "type": "string",
                    "description": "Caminho relativo ou absoluto do arquivo a ser lido.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Profundidade máxima de diretórios para listagem (padrão: 2).",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Limite máximo de bytes para leitura de arquivo.",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "list_files",
        workspace: str = ".",
        file_path: str = "",
        max_depth: int = 2,
        max_bytes: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        act = action.lower().strip()
        if act == "list_files":
            return self._list_files(workspace, max_depth)
        elif act == "read_file":
            limit = max_bytes if max_bytes is not None else self.default_max_bytes
            return self._read_file(file_path, limit)
        else:
            return {
                "success": False,
                "error": f"Unsupported action '{action}'. Allowed: 'list_files', 'read_file'.",
            }

    def _list_files(self, workspace: str, max_depth: int) -> dict[str, Any]:
        try:
            resolved_ws = self.guard.validate_path(workspace)
        except SecurityError as e:
            return {"success": False, "action": "list_files", "error": str(e)}

        if not resolved_ws.is_dir():
            return {
                "success": False,
                "action": "list_files",
                "error": f"Path '{workspace}' is not a directory.",
            }

        lines: list[str] = [f"📁 {resolved_ws.name}/"]

        def _walk(current: Path, depth: int, prefix: str = "") -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(
                    list(current.iterdir()),
                    key=lambda e: (not e.is_dir(), e.name.lower()),
                )
            except (PermissionError, OSError):
                return

            for i, entry in enumerate(entries):
                if entry.name in self.IGNORED_DIRS:
                    continue
                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "

                if entry.is_dir():
                    lines.append(f"{prefix}{connector}📁 {entry.name}/")
                    _walk(entry, depth + 1, prefix + sub_prefix)
                else:
                    lines.append(f"{prefix}{connector}📄 {entry.name}")

        _walk(resolved_ws, depth=1)
        tree_str = "\n".join(lines)
        return {
            "success": True,
            "action": "list_files",
            "workspace": str(resolved_ws),
            "tree": tree_str,
            "total_items": len(lines),
        }

    def _read_file(self, file_path: str, max_bytes: int) -> dict[str, Any]:
        if not file_path:
            return {
                "success": False,
                "action": "read_file",
                "error": "file_path is required for read_file action.",
            }

        try:
            resolved_path = self.guard.validate_path(file_path)
        except SecurityError as e:
            return {"success": False, "action": "read_file", "error": str(e)}

        if not resolved_path.is_file():
            return {
                "success": False,
                "action": "read_file",
                "error": f"File '{file_path}' does not exist or is not a file.",
            }

        try:
            with open(resolved_path, encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
                truncated = f.read(1) != ""

            return {
                "success": True,
                "action": "read_file",
                "file_path": str(resolved_path),
                "content": content,
                "truncated": truncated,
            }
        except Exception as e:
            return {"success": False, "action": "read_file", "error": str(e)}
