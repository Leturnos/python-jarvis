from typing import Any

import psutil

from core.execution.execution_plan import RiskLevel
from core.infra.logger_config import logger
from core.tools.base import BaseTool

CRITICAL_SYSTEM_PROCESSES = {
    "system",
    "system idle process",
    "registry",
    "services.exe",
    "explorer.exe",
    "svchost.exe",
    "csrss.exe",
    "smss.exe",
    "lsass.exe",
    "wininit.exe",
}


class DevPortTool(BaseTool):
    """Inspects listening local network ports and terminates hanging development server processes."""

    name = "dev_port"
    description = (
        "Inspeciona portas de rede locais (ex: 3000, 5173, 8000, 8080) e identifica processos em execução, "
        "com capacidade de encerrar servidores de desenvolvimento travados."
    )
    risk_level = RiskLevel.SAFE

    DESTRUCTIVE_ACTIONS = {"kill", "terminate", "close", "stop"}

    @classmethod
    def is_destructive_action(
        cls, action_or_params: str | dict[str, Any] | None
    ) -> bool:
        """Determines if the requested port action is destructive and terminates processes."""
        if isinstance(action_or_params, dict):
            act_str = str(action_or_params.get("action", "") or "")
        else:
            act_str = str(action_or_params or "")
        return act_str.strip().lower() in cls.DESTRUCTIVE_ACTIONS

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["inspect", "kill"],
                    "description": "'inspect' (verificar processo na porta ou listar portas) ou 'kill' (encerrar processo na porta).",
                },
                "port": {
                    "type": "integer",
                    "description": "Número da porta TCP a inspecionar ou liberar (ex: 3000, 8080).",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "inspect",
        port: int | None = None,
        authorized: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        act = (action or "inspect").strip().lower()

        if act in ("inspect", "list", "status"):
            return self._inspect_port(port=port)
        elif self.is_destructive_action(act):
            if not authorized:
                logger.warning(
                    f"Refusing unauthenticated kill request on port {port} without authorization."
                )
                return {
                    "success": False,
                    "action": "kill",
                    "error": (
                        "Ação destrutiva não autorizada. O encerramento de processos "
                        "exige confirmação explícita de segurança."
                    ),
                }
            return self._kill_port(port=port)
        else:
            return {
                "success": False,
                "error": f"Ação de porta desconhecida '{action}'. Use inspect ou kill.",
            }

    def _inspect_port(self, port: int | None) -> dict[str, Any]:
        try:
            connections = psutil.net_connections(kind="inet")
        except Exception as e:
            logger.error(f"Failed to query network connections via psutil: {e}")
            return {
                "success": False,
                "action": "inspect",
                "error": f"Falha ao consultar conexões de rede: {e}",
            }

        listen_conns = [c for c in connections if c.status == psutil.CONN_LISTEN]

        if port is not None:
            target_port = int(port)
            matched = [
                c for c in listen_conns if c.laddr and c.laddr.port == target_port
            ]

            if not matched:
                return {
                    "success": True,
                    "action": "inspect",
                    "port": target_port,
                    "occupied": False,
                    "message": f"A porta {target_port} está livre (nenhum processo em escuta).",
                }

            conn = matched[0]
            pid = conn.pid
            proc_info = self._get_process_info(pid)

            return {
                "success": True,
                "action": "inspect",
                "port": target_port,
                "occupied": True,
                "process": proc_info,
                "message": (
                    f"A porta {target_port} está ocupada pelo processo '{proc_info.get('name')}' "
                    f"(PID: {pid})."
                ),
            }

        # List all dev listening ports (ports >= 1024)
        active_ports = []
        seen_ports = set()
        for c in sorted(listen_conns, key=lambda x: x.laddr.port if x.laddr else 0):
            if c.laddr and c.laddr.port >= 1024 and c.laddr.port not in seen_ports:
                seen_ports.add(c.laddr.port)
                proc_info = self._get_process_info(c.pid)
                active_ports.append(
                    {
                        "port": c.laddr.port,
                        "ip": c.laddr.ip,
                        "pid": c.pid,
                        "process_name": proc_info.get("name", "Desconhecido"),
                    }
                )

        return {
            "success": True,
            "action": "inspect",
            "count": len(active_ports),
            "ports": active_ports[:20],
        }

    def _kill_port(self, port: int | None) -> dict[str, Any]:
        if port is None or int(port) <= 0 or int(port) > 65535:
            return {
                "success": False,
                "action": "kill",
                "error": "Informe uma porta válida entre 1 e 65535 para encerrar o processo.",
            }

        target_port = int(port)
        try:
            connections = psutil.net_connections(kind="inet")
        except Exception as e:
            return {"success": False, "action": "kill", "error": str(e)}

        matched = [
            c
            for c in connections
            if c.status == psutil.CONN_LISTEN
            and c.laddr
            and c.laddr.port == target_port
        ]

        if not matched or not matched[0].pid:
            return {
                "success": False,
                "action": "kill",
                "port": target_port,
                "error": f"Nenhum processo foi encontrado escutando na porta {target_port}.",
            }

        pid = matched[0].pid
        if pid <= 4:
            return {
                "success": False,
                "action": "kill",
                "error": f"Operação bloqueada: o PID {pid} pertence ao Kernel/Sistema do Windows.",
            }

        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()

            if proc_name.lower() in CRITICAL_SYSTEM_PROCESSES:
                return {
                    "success": False,
                    "action": "kill",
                    "error": f"Operação bloqueada: o processo '{proc_name}' é um serviço crítico do Windows.",
                }

            proc.terminate()
            gone, alive = psutil.wait_procs([proc], timeout=3.0)
            if alive:
                proc.kill()

            logger.info(
                f"Successfully killed process '{proc_name}' (PID: {pid}) occupying port {target_port}."
            )
            return {
                "success": True,
                "action": "kill",
                "port": target_port,
                "killed_pid": pid,
                "killed_process": proc_name,
                "message": f"Processo '{proc_name}' (PID: {pid}) na porta {target_port} finalizado com sucesso.",
            }
        except psutil.NoSuchProcess:
            return {
                "success": True,
                "action": "kill",
                "message": f"O processo na porta {target_port} já havia sido encerrado.",
            }
        except (psutil.AccessDenied, PermissionError) as e:
            return {
                "success": False,
                "action": "kill",
                "error": f"Acesso negado ao tentar finalizar processo PID {pid}: execute como Administrador se necessário. ({e})",
            }
        except Exception as e:
            logger.error(f"Error killing process on port {target_port}: {e}")
            return {"success": False, "action": "kill", "error": str(e)}

    @staticmethod
    def _get_process_info(pid: int | None) -> dict[str, Any]:
        if not pid:
            return {"pid": None, "name": "Desconhecido"}
        try:
            proc = psutil.Process(pid)
            mem_mb = round(proc.memory_info().rss / (1024 * 1024), 1)
            cmd = " ".join(proc.cmdline()[:4])
            return {
                "pid": pid,
                "name": proc.name(),
                "memory_mb": mem_mb,
                "command_sample": cmd,
            }
        except Exception:
            return {"pid": pid, "name": "Desconhecido"}
