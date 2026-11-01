import json
import os
import subprocess
from pathlib import Path
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.security.path_guard import PathGuard
from core.shared.errors import SecurityError
from core.tools.base import BaseTool


class GitHubTool(BaseTool):
    """Integrates with GitHub CLI (gh) to query pull requests, issues, and workflow runs in authorized workspaces."""

    name = "github"
    description = (
        "Consulta Pull Requests, Issues e status de CI do GitHub Actions via GitHub CLI (gh) "
        "em repositórios autorizados."
    )
    risk_level = RiskLevel.SAFE

    def __init__(self, path_guard: PathGuard | None = None) -> None:
        self.guard = path_guard or PathGuard()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["pr_list", "pr_status", "issue_list", "ci_status"],
                    "description": "Ação a consultar: 'pr_list' (PRs abertos), 'pr_status' (status dos meus PRs), 'issue_list' (issues abertas) ou 'ci_status' (GitHub Actions).",
                },
                "workspace": {
                    "type": "string",
                    "description": "Caminho do repositório autorizado (padrão: workspace atual '.').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Limite máximo de itens a listar (padrão: 10).",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "pr_list",
        workspace: str = ".",
        limit: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            resolved_ws = self.guard.validate_path(workspace)
        except SecurityError as e:
            return {"success": False, "error": str(e)}

        act = (action or "pr_list").strip().lower()
        lim = max(1, min(limit, 30))

        if act == "pr_list":
            return self._gh_pr_list(resolved_ws, lim)
        elif act == "pr_status":
            return self._gh_pr_status(resolved_ws)
        elif act == "issue_list":
            return self._gh_issue_list(resolved_ws, lim)
        elif act in ("ci_status", "actions_status", "runs"):
            return self._gh_ci_status(resolved_ws, lim)
        else:
            return {
                "success": False,
                "error": f"Ação GitHub desconhecida '{action}'. Use pr_list, pr_status, issue_list ou ci_status.",
            }

    def _run_gh(
        self, cmd: list[str], workspace: Path, timeout: float = 15.0
    ) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "NO_COLOR": "1"}
        return subprocess.run(
            cmd,
            cwd=workspace,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
            env=env,
        )

    def _gh_pr_list(self, workspace: Path, limit: int) -> dict[str, Any]:
        cmd = [
            "gh",
            "pr",
            "list",
            "--limit",
            str(limit),
            "--json",
            "number,title,author,headRefName,url,isDraft",
        ]
        try:
            proc = self._run_gh(cmd, workspace)
            data = json.loads(proc.stdout) if proc.stdout.strip() else []
            return {
                "success": True,
                "action": "pr_list",
                "count": len(data),
                "pull_requests": data,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "action": "pr_list",
                "error": "GitHub CLI ('gh') não foi encontrado no PATH do sistema.",
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "pr_list", "error": err}
        except Exception as e:
            return {"success": False, "action": "pr_list", "error": str(e)}

    def _gh_pr_status(self, workspace: Path) -> dict[str, Any]:
        cmd = [
            "gh",
            "pr",
            "status",
            "--json",
            "currentBranch,createdBy,needsReview",
        ]
        try:
            proc = self._run_gh(cmd, workspace)
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
            return {"success": True, "action": "pr_status", "status": data}
        except FileNotFoundError:
            return {
                "success": False,
                "action": "pr_status",
                "error": "GitHub CLI ('gh') não foi encontrado no PATH do sistema.",
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "pr_status", "error": err}
        except Exception as e:
            return {"success": False, "action": "pr_status", "error": str(e)}

    def _gh_issue_list(self, workspace: Path, limit: int) -> dict[str, Any]:
        cmd = [
            "gh",
            "issue",
            "list",
            "--limit",
            str(limit),
            "--json",
            "number,title,author,labels,url",
        ]
        try:
            proc = self._run_gh(cmd, workspace)
            data = json.loads(proc.stdout) if proc.stdout.strip() else []
            return {
                "success": True,
                "action": "issue_list",
                "count": len(data),
                "issues": data,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "action": "issue_list",
                "error": "GitHub CLI ('gh') não foi encontrado no PATH do sistema.",
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "issue_list", "error": err}
        except Exception as e:
            return {"success": False, "action": "issue_list", "error": str(e)}

    def _gh_ci_status(self, workspace: Path, limit: int) -> dict[str, Any]:
        cmd = [
            "gh",
            "run",
            "list",
            "--limit",
            str(limit),
            "--json",
            "databaseId,displayTitle,status,conclusion,workflowName,headBranch",
        ]
        try:
            proc = self._run_gh(cmd, workspace)
            data = json.loads(proc.stdout) if proc.stdout.strip() else []
            return {
                "success": True,
                "action": "ci_status",
                "count": len(data),
                "runs": data,
            }
        except FileNotFoundError:
            return {
                "success": False,
                "action": "ci_status",
                "error": "GitHub CLI ('gh') não foi encontrado no PATH do sistema.",
            }
        except subprocess.CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            return {"success": False, "action": "ci_status", "error": err}
        except Exception as e:
            return {"success": False, "action": "ci_status", "error": str(e)}
