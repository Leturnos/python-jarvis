from typing import Any

import pytest

from core.execution.execution_plan import RiskLevel
from core.tools.base import BaseTool
from core.tools.tool_registry import ToolRegistry


class DummyTool(BaseTool):
    name = "dummy_tool"
    description = "A dummy tool for unit testing."
    risk_level = RiskLevel.SAFE

    def execute(self, message: str = "hello", **kwargs: Any) -> dict[str, Any]:
        return {"success": True, "echo": message}

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to echo"}
            },
        }


def test_base_tool_abstract_enforcement():
    with pytest.raises(TypeError):
        BaseTool()  # type: ignore


def test_tool_registry_register_and_get():
    registry = ToolRegistry()
    tool = DummyTool()
    registry.register(tool)

    assert registry.get_tool("dummy_tool") is tool
    assert "dummy_tool" in [t.name for t in registry.list_tools()]
    assert registry.get_available_tool_names() == ["dummy_tool"]


def test_tool_registry_execute_success():
    registry = ToolRegistry()
    registry.register(DummyTool())

    result = registry.execute_tool("dummy_tool", message="Jarvis Test")
    assert result["success"] is True
    assert result["echo"] == "Jarvis Test"


def test_tool_registry_execute_not_found():
    registry = ToolRegistry()
    result = registry.execute_tool("non_existent_tool")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_tool_registry_prompt_description():
    registry = ToolRegistry()
    registry.register(DummyTool())

    prompt_desc = registry.get_tools_prompt_description()
    assert "dummy_tool" in prompt_desc
    assert "A dummy tool for unit testing." in prompt_desc
    assert "message" in prompt_desc


def test_init_default_tools():
    from core.tools.tool_registry import init_default_tools

    test_reg = ToolRegistry()
    init_default_tools(test_reg)
    tool_names = [t.name for t in test_reg.list_tools()]
    assert "web_search" in tool_names
    assert "git" in tool_names
    assert "project_inspect" in tool_names
    assert "weather" in tool_names
    assert "finance" in tool_names
    assert "calculator" in tool_names
