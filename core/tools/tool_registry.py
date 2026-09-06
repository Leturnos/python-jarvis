from typing import Any

from core.infra.logger_config import logger
from core.persistence.history_db import history_manager
from core.tools.base import BaseTool


class ToolRegistry:
    """Catalog and dispatcher for scoped tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance in the catalog."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool '{tool.name}' (Risk: {tool.risk_level.value})")

    def get_tool(self, name: str) -> BaseTool | None:
        """Retrieves a registered tool by its name."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """Lists all registered tools."""
        return list(self._tools.values())

    def get_tools_prompt_description(self) -> str:
        """Generates a structured text block of available tools for the LLM prompt."""
        if not self._tools:
            return "Nenhuma ferramenta externa registrada."

        lines = []
        for tool in self._tools.values():
            params = tool.get_parameters_schema()
            props = params.get("properties", {})
            props_summary = ", ".join(
                f"{k} ({v.get('type', 'any')}: {v.get('description', '')})"
                for k, v in props.items()
            )
            lines.append(
                f"- Tool: '{tool.name}' | Risco: {tool.risk_level.value} | "
                f"Parâmetros: [{props_summary}] | Descrição: {tool.description}"
            )
        return "\n".join(lines)

    def execute_tool(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Executes a tool by name with error handling and telemetry."""
        tool = self.get_tool(name)
        if not tool:
            logger.warning(f"Attempted to execute unregistered tool: '{name}'")
            return {"success": False, "error": f"Tool '{name}' not found."}

        logger.info(f"Executing tool '{name}' with params: {kwargs}")
        try:
            result = tool.execute(**kwargs)
            history_manager.log_metric(f"tool_exec_{name}_success", 1.0)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            history_manager.log_metric(f"tool_exec_{name}_error", 1.0)
            return {"success": False, "error": str(e)}


tool_registry = ToolRegistry()


def init_default_tools(registry: ToolRegistry | None = None) -> None:
    """Initializes default scoped tools based on configuration."""
    from core.infra.config import config
    from core.tools.git_tool import ScopedGitTool
    from core.tools.project_tool import ProjectInspectTool
    from core.tools.web_search_tool import WebSearchTool

    target = registry or tool_registry
    tools_cfg = config.get("tools", {})

    if tools_cfg.get("web_search", {}).get("enabled", True):
        target.register(WebSearchTool())
    if tools_cfg.get("developer", {}).get("enabled", True):
        target.register(ScopedGitTool())
        target.register(ProjectInspectTool())


init_default_tools()
