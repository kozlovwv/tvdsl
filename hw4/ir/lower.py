"""Lower the checked HW3 AST to typed instructions and explicit basic blocks."""

from funny import ast as a
from sema.annotated import to_json
from .model import Block, Function, Instr
from .runtime import int32


class Builder:
    def __init__(self, node):
        variables = node.params + node.returns + node.uses
        self.f = Function(node.name, [v.name for v in node.params], [v.name for v in node.returns],
                          {v.name: v.type for v in variables}, [])
        self.current = self.block()
        self.count = 0

    def block(self):
        b = Block(f"B{len(self.f.blocks)}")
        self.f.blocks.append(b)
        return b

    def emit(self, op, dest=(), args=(), target=(), name=""):
        self.current.code.append(Instr(op, list(dest), list(args), list(target), name))

    def temp(self, typ):
        self.count += 1
        name = f"%{self.count}"
        self.f.types[name] = typ
        return name

    def expr(self, e):
        if isinstance(e, a.Num):
            return int32(e.value)
        if isinstance(e, a.BoolLit):
            return e.value
        if isinstance(e, a.Var):
            return e.name
        t = self.temp(e.type)
        if isinstance(e, a.Unary):
            self.emit("neg" if e.op == "-" else "not", [t], [self.expr(e.operand)])
        elif isinstance(e, a.Binary):
            self.emit(e.op, [t], [self.expr(e.left), self.expr(e.right)])
        elif isinstance(e, a.Index):
            self.emit("load", [t], [e.array, self.expr(e.index)])
        elif isinstance(e, a.Update):
            self.emit("update", [t], [self.expr(e.array), self.expr(e.index), self.expr(e.value)])
        elif isinstance(e, a.Call):
            self.emit("length" if e.name == "length" else "call", [t],
                      [self.expr(x) for x in e.args], name="" if e.name == "length" else e.name)
        else:
            raise ValueError(f"unsupported executable expression: {type(e).__name__}")
        return t

    def annotation(self, kind, pred):
        if pred is not None:
            self.f.annotations.append({"kind": kind, "block": self.current.label,
                                       "source": to_json(pred.pos), "predicate": to_json(pred)})

    def stmt(self, s):
        if isinstance(s, a.Block):
            for child in s.stmts:
                self.stmt(child)
        elif isinstance(s, a.Assign):
            self.emit("copy", [s.target], [self.expr(s.value)])
        elif isinstance(s, a.MultiAssign):
            values = [self.expr(x) for x in s.call.args]
            temps = [self.temp(self.f.types[x]) for x in s.targets]
            self.emit("call", temps, values, name=s.call.name)
            for dest, value in zip(s.targets, temps):
                self.emit("copy", [dest], [value])
        elif isinstance(s, a.If):
            cond = self.expr(s.cond)
            yes, no, end = self.block(), self.block(), self.block()
            self.emit("branch", args=[cond], target=[yes.label, no.label])
            self.current = yes
            self.stmt(s.then)
            self.emit("jump", target=[end.label])
            self.current = no
            if s.else_ is not None:
                self.stmt(s.else_)
            self.emit("jump", target=[end.label])
            self.current = end
        elif isinstance(s, a.While):
            head, body, end = self.block(), self.block(), self.block()
            self.emit("jump", target=[head.label])
            self.current = head
            self.annotation("invariant", s.invariant)
            self.emit("branch", args=[self.expr(s.cond)], target=[body.label, end.label])
            self.current = body
            self.stmt(s.body)
            self.emit("jump", target=[head.label])
            self.current = end
        elif isinstance(s, (a.Assert, a.Assume)):
            self.annotation("assert" if isinstance(s, a.Assert) else "assume", s.pred)
        else:
            raise ValueError(f"unsupported statement: {type(s).__name__}")


def lower(program):
    functions, formulas = [], []
    for node in program.items:
        if isinstance(node, a.Formula):
            formulas.append(to_json(node))
            continue
        b = Builder(node)
        b.annotation("requires", node.requires)
        b.stmt(node.body)
        b.annotation("ensures", node.ensures)
        b.emit("return", args=b.f.returns)
        functions.append(b.f)
    return functions, formulas
