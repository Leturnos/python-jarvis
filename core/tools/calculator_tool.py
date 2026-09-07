import ast
import operator
from collections.abc import Callable
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.logger_config import logger
from core.tools.base import BaseTool


class CalculatorTool(BaseTool):
    """Safely evaluates mathematical expressions via AST and converts common units."""

    name = "calculator"
    description = (
        "Calcula expressões matemáticas com segurança (sem eval) e realiza "
        "conversões de unidades (km/mi, kg/lb, °C/°F, MB/GB)."
    )
    risk_level = RiskLevel.SAFE

    ALLOWED_OPERATORS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    ALLOWED_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # Unit conversion rates to a common base within each category
    LENGTH_CONVERSIONS: dict[str, float] = {
        "m": 1.0,
        "km": 1000.0,
        "cm": 0.01,
        "mm": 0.001,
        "mi": 1609.344,
        "yd": 0.9144,
        "ft": 0.3048,
        "in": 0.0254,
    }

    MASS_CONVERSIONS: dict[str, float] = {
        "kg": 1.0,
        "g": 0.001,
        "mg": 0.000001,
        "lb": 0.45359237,
        "oz": 0.028349523125,
    }

    DATA_CONVERSIONS: dict[str, float] = {
        "b": 1.0,
        "kb": 1024.0,
        "mb": 1024.0**2,
        "gb": 1024.0**3,
        "tb": 1024.0**4,
    }

    UNIT_ALIASES: dict[str, str] = {
        # Temperature
        "celsius": "c",
        "fahrenheit": "f",
        "kelvin": "k",
        # Length
        "quilometros": "km",
        "quilometro": "km",
        "kilometros": "km",
        "kilometro": "km",
        "metros": "m",
        "metro": "m",
        "centimetros": "cm",
        "centimetro": "cm",
        "milimetros": "mm",
        "milimetro": "mm",
        "milhas": "mi",
        "milha": "mi",
        "polegadas": "in",
        "polegada": "in",
        "pes": "ft",
        "pe": "ft",
        "jardas": "yd",
        "jarda": "yd",
        # Mass
        "quilogramas": "kg",
        "quilograma": "kg",
        "quilos": "kg",
        "quilo": "kg",
        "gramas": "g",
        "grama": "g",
        "miligramas": "mg",
        "miligrama": "mg",
        "libras": "lb",
        "libra": "lb",
        "oncas": "oz",
        "onca": "oz",
        # Data
        "bytes": "b",
        "byte": "b",
        "kilobytes": "kb",
        "kilobyte": "kb",
        "megabytes": "mb",
        "megabyte": "mb",
        "gigabytes": "gb",
        "gigabyte": "gb",
        "terabytes": "tb",
        "terabyte": "tb",
    }

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Expressão matemática para calcular (ex: '150 * 1.15', '2 ** 10').",
                },
                "convert_value": {
                    "type": "number",
                    "description": "Valor numérico para converter entre unidades.",
                },
                "from_unit": {
                    "type": "string",
                    "description": "Unidade de origem (ex: 'km', 'mi', 'c', 'f', 'kg', 'lb', 'gb', 'mb').",
                },
                "to_unit": {
                    "type": "string",
                    "description": "Unidade de destino (ex: 'km', 'mi', 'c', 'f', 'kg', 'lb', 'gb', 'mb').",
                },
            },
        }

    def execute(
        self,
        expression: str | None = None,
        convert_value: float | int | None = None,
        from_unit: str | None = None,
        to_unit: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if convert_value is not None and from_unit and to_unit:
            try:
                num_val = float(convert_value)
            except (ValueError, TypeError):
                return {
                    "success": False,
                    "error": f"Valor numérico inválido para conversão: '{convert_value}'.",
                }
            return self._convert_units(num_val, from_unit, to_unit)

        if expression:
            return self._evaluate_math(expression)

        return {
            "success": False,
            "error": "Forneça uma expressão matemática ou valores para conversão de unidades.",
        }

    def _evaluate_math(self, expression: str) -> dict[str, Any]:
        clean_expr = expression.strip()
        try:
            tree = ast.parse(clean_expr, mode="eval")
            result = self._eval_ast_node(tree.body)
            return {
                "success": True,
                "operation": "calculate",
                "expression": clean_expr,
                "result": result,
            }
        except ZeroDivisionError:
            return {
                "success": False,
                "error": "Divisão por zero não é permitida.",
            }
        except ValueError as ve:
            return {"success": False, "error": str(ve)}
        except Exception as e:
            logger.warning(f"CalculatorTool AST parse error: {e}")
            return {
                "success": False,
                "error": f"Expressão matemática inválida ou não permitida: '{clean_expr}'.",
            }

    def _eval_ast_node(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Literal não numérico não permitido: {node.value!r}")

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self.ALLOWED_OPERATORS:
                raise ValueError(f"Operador não permitido: {op_type.__name__}")

            left = self._eval_ast_node(node.left)
            right = self._eval_ast_node(node.right)

            # Prevent CPU denial of service with huge exponents
            if op_type is ast.Pow:
                if right > 1000 or abs(left) > 1000000:
                    raise ValueError("Expoente excessivo para cálculo.")

            op_fn = self.ALLOWED_OPERATORS[op_type]
            res: float | int = op_fn(left, right)
            return res

        if isinstance(node, ast.UnaryOp):
            unary_op_type = type(node.op)
            if unary_op_type not in self.ALLOWED_UNARY_OPERATORS:
                raise ValueError(
                    f"Operador unário não permitido: {unary_op_type.__name__}"
                )

            operand = self._eval_ast_node(node.operand)
            unary_op_fn = self.ALLOWED_UNARY_OPERATORS[unary_op_type]
            unary_res: float | int = unary_op_fn(operand)
            return unary_res

        raise ValueError(f"Expressão contém nó não permitido: {type(node).__name__}")

    def _convert_units(self, value: float, from_u: str, to_u: str) -> dict[str, Any]:
        f_clean = from_u.strip().lower()
        t_clean = to_u.strip().lower()
        f = self.UNIT_ALIASES.get(f_clean, f_clean)
        t = self.UNIT_ALIASES.get(t_clean, t_clean)

        # Temperature
        if f in {"c", "f", "k"} and t in {"c", "f", "k"}:
            c_val = value
            if f == "f":
                c_val = (value - 32.0) * (5.0 / 9.0)
            elif f == "k":
                c_val = value - 273.15

            res = c_val
            if t == "f":
                res = c_val * (9.0 / 5.0) + 32.0
            elif t == "k":
                res = c_val + 273.15

            return {
                "success": True,
                "operation": "convert",
                "from_value": value,
                "from_unit": f.upper(),
                "to_unit": t.upper(),
                "result": round(res, 4),
            }

        # Length
        if f in self.LENGTH_CONVERSIONS and t in self.LENGTH_CONVERSIONS:
            base_m = value * self.LENGTH_CONVERSIONS[f]
            res = base_m / self.LENGTH_CONVERSIONS[t]
            return {
                "success": True,
                "operation": "convert",
                "from_value": value,
                "from_unit": f,
                "to_unit": t,
                "result": round(res, 4),
            }

        # Mass
        if f in self.MASS_CONVERSIONS and t in self.MASS_CONVERSIONS:
            base_kg = value * self.MASS_CONVERSIONS[f]
            res = base_kg / self.MASS_CONVERSIONS[t]
            return {
                "success": True,
                "operation": "convert",
                "from_value": value,
                "from_unit": f,
                "to_unit": t,
                "result": round(res, 4),
            }

        # Data
        if f in self.DATA_CONVERSIONS and t in self.DATA_CONVERSIONS:
            base_bytes = value * self.DATA_CONVERSIONS[f]
            res = base_bytes / self.DATA_CONVERSIONS[t]
            return {
                "success": True,
                "operation": "convert",
                "from_value": value,
                "from_unit": f,
                "to_unit": t,
                "result": round(res, 4),
            }

        return {
            "success": False,
            "error": f"Unidades incompatíveis ou não suportadas: '{from_u}' e '{to_u}'.",
        }
