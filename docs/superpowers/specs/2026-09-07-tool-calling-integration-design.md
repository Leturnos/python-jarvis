# Design Specification: Universal Tool Calling & Dynamic Tool Dispatch Architecture

**Date:** 2026-09-07  
**Status:** Approved  
**Target:** `python-jarvis`

---

## 1. Overview & Goals

Earlier versions of Jarvis dispatched automation actions through rigid, hardcoded conditional branches inside `ActionDispatcher`. When new integrations were developed (such as web search or developer tools), modifying the dispatcher, prompt builders, and parameter parsers was required across multiple distinct modules.

This specification introduces a **Universal Dynamic Tool Calling Architecture**:
1. **Abstract Tool Interface (`BaseTool`):** Enforces a standardized contract for all capabilities, encapsulating metadata, JSON parameter schemas, risk levels, and execution logic.
2. **Central Tool Registry (`ToolRegistry`):** Provides runtime tool registration, discovery, parameter validation, and telemetry tracking.
3. **Automated LLM Schema Injection:** Dynamically extracts JSON Schema declarations from registered tools and binds them into LiteLLM request payloads.
4. **Execution Governance & Isolation:** Sandboxes tool executions with timeout guards, error wrapping, and security checks before execution.

---

## 2. Architecture & Execution Flow

```mermaid
flowchart TD
    UserQuery["User Input (Voice / Palette)"] --> LLM["LLMAgent"]
    
    subgraph RegistryCatalog ["Tool Discovery & Catalog"]
        Registry["ToolRegistry (core/tools/tool_registry.py)"]
        Tool1["BaseTool: Weather"]
        Tool2["BaseTool: WebSearch"]
        ToolN["BaseTool: Custom Scoped Tool"]
        
        Tool1 --> Registry
        Tool2 --> Registry
        ToolN --> Registry
    end
    
    Registry -->|Dynamic JSON Schemas| LLM
    LLM -->|tool_calls: {name, arguments}| Dispatcher["ActionDispatcher"]
    
    Dispatcher -->|Execute via Registry| Registry
    Registry -->|Execution Guard & Telemetry| TargetTool["Target BaseTool.execute()"]
    TargetTool -->|Result Payload| ResultFormatter["LLMAgent.synthesize_tool_response"]
    ResultFormatter --> TTS["Spoken Feedback & UI Display"]
```

---

## 3. Subsystem Specifications

### 3.1 Base Tool Interface (`core/tools/base.py`)
```python
class BaseTool(ABC):
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.SAFE
    
    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """Returns standard JSON Schema dict defining expected parameters."""
        pass
        
    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Executes the tool logic and returns a structured ToolResult."""
        pass
```

### 3.2 Tool Registry (`core/tools/tool_registry.py`)
- **Lifecycle:** Instantiated as a singleton or injected dependency during bootstrap.
- **Responsibilities:**
  - `register_tool(tool: BaseTool) -> None`: Validates unique tool naming and registers instance.
  - `get_tool_schemas() -> list[dict]`: Compiles all active tools into standard OpenAI/LiteLLM function calling schemas.
  - `execute_tool(name: str, args: dict) -> ToolResult`:
    1. Resolves tool instance by name.
    2. Validates parameters against `parameters_schema`.
    3. Records start timestamp.
    4. Executes within a protected `try/except` block with a 10-second watchdog timeout.
    5. Dispatches execution telemetry to `history_manager`.

### 3.3 Seamless Dispatcher Integration (`core/execution/dispatcher.py`)
- The `ActionDispatcher` inspects LLM responses. If `type == "tool_call"`, it routes execution directly through `tool_registry.execute_tool()`.
- If the tool's `risk_level` is `RiskLevel.DANGEROUS` (such as terminating processes or wiping databases), the dispatcher automatically triggers the `SecurityDialogWidget` to request explicit user authorization.
