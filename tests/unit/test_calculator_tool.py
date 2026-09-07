from core.execution.execution_plan import RiskLevel
from core.tools.calculator_tool import CalculatorTool


def test_calculator_tool_metadata() -> None:
    tool = CalculatorTool()
    assert tool.name == "calculator"
    assert tool.risk_level == RiskLevel.SAFE
    schema = tool.get_parameters_schema()
    assert "expression" in schema["properties"]
    assert "from_unit" in schema["properties"]


def test_calculator_arithmetic_basic() -> None:
    tool = CalculatorTool()
    result = tool.execute(expression="15 + 27 * 2")
    assert result["success"] is True
    assert result["operation"] == "calculate"
    assert result["result"] == 69


def test_calculator_arithmetic_complex() -> None:
    tool = CalculatorTool()
    result = tool.execute(expression="(150 + 80) * 1.15")
    assert result["success"] is True
    assert round(result["result"], 2) == 264.5


def test_calculator_powers_and_modulus() -> None:
    tool = CalculatorTool()
    result = tool.execute(expression="2 ** 10 + 15 % 4")
    assert result["success"] is True
    assert result["result"] == 1027


def test_calculator_division_by_zero() -> None:
    tool = CalculatorTool()
    result = tool.execute(expression="100 / 0")
    assert result["success"] is False
    assert "zero" in result["error"].lower()


def test_calculator_blocks_unsafe_code_execution() -> None:
    tool = CalculatorTool()
    unsafe_expressions = [
        "__import__('os').system('dir')",
        "eval('2 + 2')",
        "open('test.txt')",
        "print('hello')",
        "x + 1",
    ]
    for expr in unsafe_expressions:
        result = tool.execute(expression=expr)
        assert result["success"] is False
        assert (
            "não permitid" in result["error"].lower()
            or "inválida" in result["error"].lower()
        )


def test_calculator_blocks_excessive_exponent() -> None:
    tool = CalculatorTool()
    result = tool.execute(expression="9 ** 999999")
    assert result["success"] is False
    assert "expoente excessivo" in result["error"].lower()


def test_calculator_unit_conversion_distance() -> None:
    tool = CalculatorTool()
    result = tool.execute(convert_value=100.0, from_unit="km", to_unit="mi")
    assert result["success"] is True
    assert result["operation"] == "convert"
    assert round(result["result"], 2) == 62.14


def test_calculator_unit_conversion_temperature() -> None:
    tool = CalculatorTool()
    # Celsius to Fahrenheit: 25 * 9/5 + 32 = 77
    result = tool.execute(convert_value=25.0, from_unit="c", to_unit="f")
    assert result["success"] is True
    assert result["result"] == 77.0


def test_calculator_unit_conversion_weight() -> None:
    tool = CalculatorTool()
    result = tool.execute(convert_value=10.0, from_unit="kg", to_unit="lb")
    assert result["success"] is True
    assert round(result["result"], 2) == 22.05


def test_calculator_invalid_units() -> None:
    tool = CalculatorTool()
    result = tool.execute(convert_value=10.0, from_unit="km", to_unit="kg")
    assert result["success"] is False
    assert (
        "incompatíveis" in result["error"].lower()
        or "não suportada" in result["error"].lower()
    )


def test_calculator_unit_conversion_aliases() -> None:
    tool = CalculatorTool()
    # Test temperature with full names
    result_temp = tool.execute(
        convert_value=25.0, from_unit="celsius", to_unit="fahrenheit"
    )
    assert result_temp["success"] is True
    assert result_temp["result"] == 77.0

    # Test distance with full names
    result_dist = tool.execute(
        convert_value=10.0, from_unit="quilometros", to_unit="milhas"
    )
    assert result_dist["success"] is True
    assert round(result_dist["result"], 2) == 6.21


def test_calculator_invalid_convert_value() -> None:
    tool = CalculatorTool()
    result = tool.execute(convert_value="invalid_number", from_unit="km", to_unit="mi")  # type: ignore
    assert result["success"] is False
    assert "inválido" in result["error"].lower()
