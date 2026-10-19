"""AST of a Funny module, its JSON form and a readable text dump.

Every node has `pos`: the position of the token that names the node - the operator of a Binary/Unary,
the name of a Var/Call/Function, the keyword of an If/While/Assert, the "{" of a Block,
the first target of an assignment. See README.md for the format.
"""

from dataclasses import dataclass, fields
from typing import Any

from .lexer import Pos


# ---------- Expressions ----------

@dataclass
class Num:
    value: int
    pos: Pos


@dataclass
class BoolLit:
    value: bool
    pos: Pos


@dataclass
class Var:
    name: str
    pos: Pos


@dataclass
class Index:
    """a[i]: only a variable can be indexed."""
    array: str
    index: "Expr"
    pos: Pos


@dataclass
class Call:
    """Function call f(...) in an expression, including the builtin length(a)."""
    name: str
    args: list["Expr"]
    pos: Pos


@dataclass
class FormulaRef:
    """f(...) where a truth value is needed: a reference to a formula (predicates only)."""
    name: str
    args: list["Expr"]
    pos: Pos


@dataclass
class Unary:
    op: str  # "-" or "not"
    operand: "Expr"
    pos: Pos


@dataclass
class Binary:
    op: str  # + - * /   == != < <= > >=   and or ->
    left: "Expr"
    right: "Expr"
    pos: Pos


@dataclass
class Quantifier:
    kind: str  # "forall" or "exists"
    var: "VarDef"
    body: "Expr"
    pos: Pos


@dataclass
class Update:
    """Functional array update: a copy of `array` with `index` set to `value`.
    Produced only by desugaring a[i] = v into a = Update(a, i, v)."""
    array: "Expr"
    index: "Expr"
    value: "Expr"
    pos: Pos


Expr = Num | BoolLit | Var | Index | Call | FormulaRef | Unary | Binary | Quantifier | Update


# ---------- Statements ----------

@dataclass
class Block:
    stmts: list["Stmt"]
    pos: Pos


@dataclass
class Assign:
    target: str
    value: Expr
    pos: Pos


@dataclass
class MultiAssign:
    targets: list[str]
    call: Call
    pos: Pos


@dataclass
class If:
    cond: Expr
    then: "Stmt"
    else_: "Stmt | None"
    pos: Pos


@dataclass
class While:
    cond: Expr
    invariant: Expr | None
    body: "Stmt"
    pos: Pos


@dataclass
class Assert:
    pred: Expr
    pos: Pos


@dataclass
class Assume:
    pred: Expr
    pos: Pos


Stmt = Block | Assign | MultiAssign | If | While | Assert | Assume


# ---------- Declarations ----------

@dataclass
class VarDef:
    name: str
    type: str | None  # "int", "int[]", or None for a local declared in `uses` without a type
    pos: Pos


@dataclass
class Function:
    name: str
    params: list[VarDef]
    requires: Expr | None  # None: not written (the default is true)
    returns: list[VarDef]
    ensures: Expr | None  # None: not written
    uses: list[VarDef]
    body: Stmt
    pos: Pos


@dataclass
class Formula:
    name: str
    params: list[VarDef]
    body: Expr
    pos: Pos


@dataclass
class Program:
    items: list[Function | Formula]


Node = Expr | Stmt | VarDef | Function | Formula | Program


# ---------- JSON ----------

def to_json(node: Any) -> Any:
    """{"node": "Binary", "op": "+", "left": {...}, "right": {...}, "pos": {"line": 2, "col": 11}}."""
    if isinstance(node, list):
        return [to_json(x) for x in node]
    if isinstance(node, Pos):
        return {"line": node.line, "col": node.col}
    if hasattr(node, "__dataclass_fields__"):
        out: dict[str, Any] = {"node": type(node).__name__}
        for f in fields(node):
            out[f.name.rstrip("_")] = to_json(getattr(node, f.name))
        return out
    return node  # str, int, bool, None


# ---------- Text dump ----------

# Child fields printed without a "name:" label: their meaning is clear from the parent.
_UNLABELED = {"left", "right", "operand", "args", "stmts", "items"}


def dump(node: Node) -> str:
    """One node per line, children indented:  `Binary + @2:11`, scalar fields inline,
    child fields labelled (`cond: ...`, `then: ...`), None fields and empty lists omitted."""
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
    lines.append(f"{pad}{prefix}{type(node).__name__}{''.join(' ' + s for s in scalars)}{pos}")
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


def _scalar(value: str | int | bool) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)
