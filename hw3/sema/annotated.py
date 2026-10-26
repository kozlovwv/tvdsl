"""The annotated AST: the AST of HW2 where every expression also has `type`. JSON and text dump
in the same format as HW2 (funny/ast.py) plus the types."""

from dataclasses import fields
from typing import Any

from funny.ast import _UNLABELED, Node, VarDef, _scalar
from funny.lexer import Pos


def show(t: str | tuple[str, ...]) -> str:
    return f"({', '.join(t)})" if isinstance(t, tuple) else t


def to_json(node: Any) -> Any:
    """As in HW2, plus "type" in every expression: "int", "int[]", "bool", or a list of types for a call
    of a function with several return values."""
    if isinstance(node, list):
        return [to_json(x) for x in node]
    if isinstance(node, Pos):
        return {"line": node.line, "col": node.col}
    if hasattr(node, "__dataclass_fields__"):
        out: dict[str, Any] = {"node": type(node).__name__}
        for f in fields(node):
            out[f.name.rstrip("_")] = to_json(getattr(node, f.name))
        if hasattr(node, "type") and not isinstance(node, VarDef):
            out["type"] = list(node.type) if isinstance(node.type, tuple) else node.type
        return out
    return node


def dump(node: Node) -> str:
    """As in HW2, every expression line ends with its type:  `Binary + @2:11 : int`."""
    lines: list[str] = []
    _dump(node, 0, None, lines)
    return "\n".join(lines) + "\n"


def _dump(node: Any, depth: int, label: str | None, lines: list[str]) -> None:
    pad = "  " * depth
    prefix = f"{label}: " if label else ""
    scalars, children = [], []
    for f in fields(node):
        value = getattr(node, f.name)
        if f.name == "pos" or value is None or value == []:
            continue
        if isinstance(value, (str, int, bool)) or (isinstance(value, list) and all(isinstance(v, str) for v in value) and value):
            scalars.append(", ".join(value) if isinstance(value, list) else _scalar(value))
        else:
            children.append((f.name.rstrip("_"), value))
    pos = f" @{node.pos}" if hasattr(node, "pos") else ""
    typ = f" : {show(node.type)}" if hasattr(node, "type") and not isinstance(node, VarDef) else ""
    lines.append(f"{pad}{prefix}{type(node).__name__}{''.join(' ' + s for s in scalars)}{pos}{typ}")
    for name, value in children:
        child_label = None if name in _UNLABELED else name
        if isinstance(value, list):
            if child_label:
                lines.append(f"{pad}  {child_label}:")
                for item in value:
                    _dump(item, depth + 2, None, lines)
            else:
                for item in value:
                    _dump(item, depth + 1, None, lines)
        else:
            _dump(value, depth + 1, child_label, lines)
