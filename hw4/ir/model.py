"""Typed three-address instructions and basic blocks. Strings are variables; literals are int/bool."""

from dataclasses import dataclass, field

Operand = str | int | bool


@dataclass
class Instr:
    op: str
    dest: list[str] = field(default_factory=list)
    args: list[Operand] = field(default_factory=list)
    target: list[str] = field(default_factory=list)
    name: str = ""

    def uses(self) -> set[str]:
        return {x for x in self.args if isinstance(x, str)}


@dataclass
class Block:
    label: str
    code: list[Instr] = field(default_factory=list)

    def successors(self) -> list[str]:
        return self.code[-1].target


@dataclass
class Function:
    name: str
    params: list[str]
    returns: list[str]
    types: dict[str, str]
    blocks: list[Block]
    # Logical annotations are retained separately from executable code.
    annotations: list[dict] = field(default_factory=list)


def dump(functions: list[Function]) -> str:
    lines = []
    for f in functions:
        lines.append(f"function {f.name}({', '.join(f.params)}) returns {', '.join(f.returns)}")
        lines.append("  types: " + ", ".join(f"{v}: {t}" for v, t in f.types.items()))
        for b in f.blocks:
            lines.append(f"{b.label}:  successors=[{', '.join(b.successors())}]")
            for i in b.code:
                lhs = ", ".join(i.dest) + " = " if i.dest else ""
                args = ", ".join(str(x).lower() if isinstance(x, bool) else str(x) for x in i.args)
                suffix = " -> " + ", ".join(i.target) if i.target else ""
                lines.append(f"  {lhs}{i.op}{' ' + i.name if i.name else ''}{' ' + args if args else ''}{suffix}")
    return "\n".join(lines) + "\n"
