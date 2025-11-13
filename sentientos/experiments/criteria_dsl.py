"""Success criteria DSL parser and evaluator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Union


class CriteriaParseError(ValueError):
    """Raised when a criteria expression cannot be parsed."""


class CriteriaEvaluationError(RuntimeError):
    """Raised when a criteria expression cannot be evaluated."""


TokenValue = Union[str, int, float, bool]


@dataclass(frozen=True)
class Token:
    kind: str
    value: TokenValue


@dataclass(frozen=True)
class Literal:
    value: TokenValue


@dataclass(frozen=True)
class Identifier:
    name: str


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: "CriteriaExpression"


@dataclass(frozen=True)
class BinaryOp:
    op: str
    left: "CriteriaExpression"
    right: "CriteriaExpression"


CriteriaExpression = Union[Literal, Identifier, UnaryOp, BinaryOp]

_WHITESPACE = {" ", "\t", "\n", "\r"}
_IDENTIFIER_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
_IDENTIFIER_BODY = _IDENTIFIER_START + "0123456789"
_TWO_CHAR_OPS = {"<=", ">=", "==", "!=", "&&", "||"}
_SINGLE_CHAR_OPS = {"(", ")", "+", "-", "*", "!", "<", ">"}
_KEYWORD_OPERATORS = {"and": "&&", "or": "||", "not": "!"}


def _tokenize(expression: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    length = len(expression)
    while i < length:
        ch = expression[i]
        if ch in _WHITESPACE:
            i += 1
            continue
        if ch.isdigit() or (ch == "." and i + 1 < length and expression[i + 1].isdigit()):
            start = i
            has_dot = ch == "."
            i += 1
            while i < length:
                c = expression[i]
                if c == ".":
                    if has_dot:
                        raise CriteriaParseError("Invalid numeric literal")
                    has_dot = True
                    i += 1
                    continue
                if c.isdigit():
                    i += 1
                    continue
                break
            number_text = expression[start:i]
            try:
                value = float(number_text) if "." in number_text else int(number_text)
            except ValueError as exc:  # pragma: no cover - defensive
                raise CriteriaParseError("Invalid numeric literal") from exc
            tokens.append(Token("NUMBER", value))
            continue
        if ch in _IDENTIFIER_START:
            start = i
            i += 1
            while i < length and expression[i] in _IDENTIFIER_BODY:
                i += 1
            ident = expression[start:i]
            lowered = ident.lower()
            if lowered in ("true", "false"):
                tokens.append(Token("BOOLEAN", lowered == "true"))
            elif lowered in _KEYWORD_OPERATORS:
                tokens.append(Token("OP", _KEYWORD_OPERATORS[lowered]))
            else:
                tokens.append(Token("IDENT", ident))
            continue
        if i + 1 < length and expression[i : i + 2] in _TWO_CHAR_OPS:
            op = expression[i : i + 2]
            tokens.append(Token("OP", op))
            i += 2
            continue
        if ch in _SINGLE_CHAR_OPS:
            tokens.append(Token("OP", ch))
            i += 1
            continue
        raise CriteriaParseError(f"Unexpected character: {ch}")
    tokens.append(Token("EOF", ""))
    return tokens


class _Parser:
    def __init__(self, tokens: Iterable[Token]):
        self._tokens: Iterator[Token] = iter(tokens)
        self.current: Token = next(self._tokens)

    def _advance(self) -> None:
        self.current = next(self._tokens)

    def parse(self) -> CriteriaExpression:
        expr = self._parse_or()
        if self.current.kind != "EOF":
            raise CriteriaParseError("Unexpected trailing tokens")
        return expr

    def _parse_or(self) -> CriteriaExpression:
        expr = self._parse_and()
        while self.current.kind == "OP" and self.current.value == "||":
            op = self.current.value
            self._advance()
            right = self._parse_and()
            expr = BinaryOp(op=op, left=expr, right=right)
        return expr

    def _parse_and(self) -> CriteriaExpression:
        expr = self._parse_equality()
        while self.current.kind == "OP" and self.current.value == "&&":
            op = self.current.value
            self._advance()
            right = self._parse_equality()
            expr = BinaryOp(op=op, left=expr, right=right)
        return expr

    def _parse_equality(self) -> CriteriaExpression:
        expr = self._parse_comparison()
        while self.current.kind == "OP" and self.current.value in {"==", "!="}:
            op = self.current.value
            self._advance()
            right = self._parse_comparison()
            expr = BinaryOp(op=op, left=expr, right=right)
        return expr

    def _parse_comparison(self) -> CriteriaExpression:
        expr = self._parse_term()
        while self.current.kind == "OP" and self.current.value in {"<", "<=", ">", ">="}:
            op = self.current.value
            self._advance()
            right = self._parse_term()
            expr = BinaryOp(op=op, left=expr, right=right)
        return expr

    def _parse_term(self) -> CriteriaExpression:
        expr = self._parse_factor()
        while self.current.kind == "OP" and self.current.value in {"+", "-"}:
            op = self.current.value
            self._advance()
            right = self._parse_factor()
            expr = BinaryOp(op=op, left=expr, right=right)
        return expr

    def _parse_factor(self) -> CriteriaExpression:
        expr = self._parse_unary()
        while self.current.kind == "OP" and self.current.value == "*":
            op = self.current.value
            self._advance()
            right = self._parse_unary()
            expr = BinaryOp(op=op, left=expr, right=right)
        return expr

    def _parse_unary(self) -> CriteriaExpression:
        if self.current.kind == "OP" and self.current.value in {"!", "-"}:
            op = self.current.value
            self._advance()
            operand = self._parse_unary()
            return UnaryOp(op=op, operand=operand)
        return self._parse_primary()

    def _parse_primary(self) -> CriteriaExpression:
        token = self.current
        if token.kind == "NUMBER":
            self._advance()
            return Literal(value=token.value)
        if token.kind == "BOOLEAN":
            self._advance()
            return Literal(value=token.value)
        if token.kind == "IDENT":
            self._advance()
            return Identifier(name=token.value)
        if token.kind == "OP" and token.value == "(":
            self._advance()
            expr = self._parse_or()
            if self.current.kind != "OP" or self.current.value != ")":
                raise CriteriaParseError("Missing closing parenthesis")
            self._advance()
            return expr
        raise CriteriaParseError("Unexpected token")


def parse_criteria(expression: str) -> CriteriaExpression:
    """Parse *expression* into an AST suitable for evaluation."""

    tokens = _tokenize(expression)
    parser = _Parser(tokens)
    return parser.parse()


def _ensure_numeric(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    raise CriteriaEvaluationError(f"Expected numeric value, got {type(value).__name__}")


def _ensure_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raise CriteriaEvaluationError(f"Expected boolean value, got {type(value).__name__}")


def _evaluate(node: CriteriaExpression, context: Dict[str, Any]) -> Any:
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, Identifier):
        if node.name not in context:
            raise CriteriaEvaluationError(f"Unknown identifier: {node.name}")
        return context[node.name]
    if isinstance(node, UnaryOp):
        value = _evaluate(node.operand, context)
        if node.op == "!":
            return not _ensure_boolean(value)
        if node.op == "-":
            return -_ensure_numeric(value)
        raise CriteriaEvaluationError(f"Unsupported unary operator: {node.op}")
    if isinstance(node, BinaryOp):
        if node.op == "&&":
            left_val = _ensure_boolean(_evaluate(node.left, context))
            if not left_val:
                return False
            right_val = _ensure_boolean(_evaluate(node.right, context))
            return left_val and right_val
        if node.op == "||":
            left_val = _ensure_boolean(_evaluate(node.left, context))
            if left_val:
                return True
            right_val = _ensure_boolean(_evaluate(node.right, context))
            return right_val or left_val
        if node.op in {"+", "-", "*"}:
            left_num = _ensure_numeric(_evaluate(node.left, context))
            right_num = _ensure_numeric(_evaluate(node.right, context))
            if node.op == "+":
                return left_num + right_num
            if node.op == "-":
                return left_num - right_num
            return left_num * right_num
        left = _evaluate(node.left, context)
        right = _evaluate(node.right, context)
        if node.op == "==":
            return left == right
        if node.op == "!=":
            return left != right
        if node.op == "<":
            return _ensure_numeric(left) < _ensure_numeric(right)
        if node.op == "<=":
            return _ensure_numeric(left) <= _ensure_numeric(right)
        if node.op == ">":
            return _ensure_numeric(left) > _ensure_numeric(right)
        if node.op == ">=":
            return _ensure_numeric(left) >= _ensure_numeric(right)
        raise CriteriaEvaluationError(f"Unsupported operator: {node.op}")
    raise CriteriaEvaluationError("Unsupported expression node")


def evaluate_criteria(expr: CriteriaExpression, context: Dict[str, Any]) -> bool:
    """Evaluate parsed *expr* in *context* returning a boolean."""

    result = _evaluate(expr, context)
    return _ensure_boolean(result)


__all__ = [
    "CriteriaExpression",
    "CriteriaEvaluationError",
    "CriteriaParseError",
    "evaluate_criteria",
    "parse_criteria",
]
