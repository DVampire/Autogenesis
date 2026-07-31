'''Performs the four basic arithmetic operations (+, -, *, /) on two numbers.'''
from typing import Any, Dict
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Performs the four basic arithmetic operations (+, -, *, /) on two numbers."

_INSTRUCTION = """
## Function
Performs exactly one of the four basic arithmetic operations on two numeric operands: addition ('+'), subtraction ('-'), multiplication ('*'), or division ('/'). Returns the result as a float.

## Guidance
Use this tool for simple two-operand arithmetic. Only the four operators '+', '-', '*', '/' are supported; any other operator (including '%' or '**') is rejected with a clear error naming the unknown operator. Division by zero returns a clear division-by-zero error rather than NaN or a silent default. The numeric result is provided both in the response message text and in the structured data field as data['result'].

## Parameters
- a (float): The left operand.
- b (float): The right operand.
- op (str): The operator, one of '+', '-', '*', '/'.

## Example
{"name": "calculator_tool", "args": {"a": 6, "b": 3, "op": "/"}}
"""


@TOOL.register_module(force=True)
class CalculatorTool(Tool):
    '''Performs the four basic arithmetic operations (+, -, *, /) on two numbers.'''

    name: str = 'calculator_tool'
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description='The metadata of the tool')
    enable_evolving: bool = Field(default=False, description='Whether the tool may be evolved (self-optimized)')

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, a: float, b: float, op: str, **kwargs) -> Response:
        '''Execute one of the four basic arithmetic operations and return a Response.'''
        try:
            a = float(a)
            b = float(b)
        except (TypeError, ValueError):
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message='Operands a and b must be numeric (convertible to float). Got a={!r}, b={!r}.'.format(a, b),
            )

        if op == '+':
            result = a + b
        elif op == '-':
            result = a - b
        elif op == '*':
            result = a * b
        elif op == '/':
            if b == 0:
                return Response(
                    type=ResponseType.TOOL,
                    success=False,
                    message='Division-by-zero error: cannot divide {} by 0. Division by zero is undefined.'.format(a),
                )
            result = a / b
        else:
            return Response(
                type=ResponseType.TOOL,
                success=False,
                message="Unknown operator: '{}'. Supported operators are +, -, *, /.".format(op),
            )

        result = float(result)
        return Response(
            type=ResponseType.TOOL,
            success=True,
            message='{} {} {} = {}'.format(a, op, b, result),
            data={'result': result},
        )
