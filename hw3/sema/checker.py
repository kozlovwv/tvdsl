"""Name and type checking of a parsed Funny module; annotates every expression with its type.

Types: "int", "int[]", "bool" (conditions and predicates only, not a variable type), a tuple of types
(a call of a function with several return values, allowed only in a multiple assignment), a TVar (the
not yet known type of a local declared without a type) and ERR (the type of an erroneous expression:
it unifies with everything, so one mistake gives one message).

Two passes: first all functions and formulas are collected (calls may go forward and be recursive),
then every definition is checked. Inside a function there is one scope: parameters, return values and
locals (`uses`, or implicitly by the first assignment to an unknown name); quantifier variables are
pushed on top of it. Statements are checked in the order of the text, so a name assigned later is not
yet declared. The type of an untyped local is found by unification: the first assignment or use that
fixes it wins, a contradicting one is an error, a local whose type stays unknown is an error.
Every error is recorded and checking goes on.
"""

from dataclasses import dataclass, field

from funny.ast import (Assert, Assign, Assume, Binary, Block, BoolLit, Call, Expr, Formula, FormulaRef, Function,
                       If, Index, MultiAssign, Num, Program, Quantifier, Stmt, Unary, Update, Var, VarDef, While)
from funny.lexer import Diagnostic, Pos

INT, ARR, BOOL, ERR = "int", "int[]", "bool", "?"


class TVar:
    """Unknown type of a local. `ref` is what it is bound to (a type or another TVar);
    `origin` is where it was bound to a concrete type."""

    def __init__(self) -> None:
        self.ref: "Type | None" = None
        self.origin: Pos | None = None
        self.poisoned = False  # was assigned an erroneous value: do not report "cannot infer"


Type = str | TVar | tuple[str, ...]


def resolve(t: Type) -> Type:
    while isinstance(t, TVar) and t.ref is not None:
        t = t.ref
    return t


def origin(t: Type | None) -> Pos | None:
    while isinstance(t, TVar):
        if t.origin:
            return t.origin
        t = t.ref
    return None


def show(t: Type) -> str:
    t = resolve(t)
    if isinstance(t, tuple):
        return f"({', '.join(t)})"
    return ERR if isinstance(t, TVar) else t


def unify(a: Type, b: Type, pos: Pos) -> bool:
    a, b = resolve(a), resolve(b)
    if a is b or a == b:
        return True
    if a == ERR or b == ERR:
        for t in (a, b):
            if isinstance(t, TVar):
                t.poisoned = True
        return True
    if isinstance(b, TVar):
        a, b = b, a
    if isinstance(a, TVar):
        a.ref = b
        if not isinstance(b, TVar):
            a.origin = pos
        return True
    return False


@dataclass
class Symbol:
    kind: str  # "parameter", "return value", "local", "quantifier variable"
    type: Type
    decl: VarDef
    inferred: bool = False  # a local without a type annotation


@dataclass(frozen=True)
class Context:
    """Which variables an expression may use, and how to say it if it uses another one."""
    kinds: frozenset[str]
    rule: str = ""


BODY = Context(frozenset({"parameter", "return value", "local"}))
REQUIRES = Context(frozenset({"parameter"}), "'requires' may use only parameters")
ENSURES = Context(frozenset({"parameter", "return value"}), "'ensures' may use only parameters and return values")
FORMULA = Context(frozenset({"parameter"}))

ARITH, COMPARE, LOGIC = {"+", "-", "*", "/"}, {"==", "!=", "<", "<=", ">", ">="}, {"and", "or", "->"}


def check(program: Program) -> list[Diagnostic]:
    """Checks the module and annotates it in place: every expression gets `.type`, untyped locals get
    their inferred type in VarDef.type, implicitly declared locals are appended to Function.uses.
    Returns the errors sorted by position."""
    checker = Checker()
    checker.module(program)
    return sorted(checker.errors, key=lambda d: (d.pos.line, d.pos.col))


@dataclass
class Checker:
    errors: list[Diagnostic] = field(default_factory=list)
    items: dict[str, Function | Formula] = field(default_factory=dict)
    vars: dict[str, Symbol] = field(default_factory=dict)  # the scope of the current definition
    bound: list[Symbol] = field(default_factory=list)  # quantifier variables, innermost last
    context: Context = BODY
    typed: list[Expr] = field(default_factory=list)  # expressions of the current definition
    function: Function | None = None

    def error(self, pos: Pos, message: str) -> None:
        self.errors.append(Diagnostic(pos, message))

    # ---------- Module ----------

    def module(self, program: Program) -> None:
        for item in program.items:
            if item.name in self.items:
                first = self.items[item.name]
                self.error(item.pos, f"'{item.name}' is already defined as a {kind_of(first)} at {first.pos}")
            else:
                self.items[item.name] = item
        for item in program.items:
            self.vars, self.bound, self.typed = {}, [], []
            for p in item.params:
                self.declare(p, "parameter")
            if isinstance(item, Formula):
                self.context = FORMULA
                self.need(item.body, BOOL, f"the body of formula '{item.name}'")
            else:
                self.function_body(item)
            for e in self.typed:
                t = resolve(e.type)
                e.type = t if isinstance(t, tuple) else show(t)

    def function_body(self, fn: Function) -> None:
        self.function = fn
        for r in fn.returns:
            self.declare(r, "return value")
        for local in fn.uses:
            self.declare(local, "local")
        if fn.requires:
            self.context = REQUIRES
            self.need(fn.requires, BOOL, "the predicate of 'requires'")
        if fn.ensures:
            self.context = ENSURES
            self.need(fn.ensures, BOOL, "the predicate of 'ensures'")
        self.context = BODY
        self.stmt(fn.body)
        for name, sym in self.vars.items():
            if not sym.inferred:
                continue
            t = resolve(sym.type)
            if isinstance(t, TVar):
                if not t.poisoned:
                    self.error(sym.decl.pos, f"cannot infer the type of local '{name}': "
                                             "no assignment or use gives it a type")
            elif t != ERR:
                sym.decl.type = t

    def declare(self, vd: VarDef, kind: str) -> Symbol | None:
        if vd.name in self.vars:
            first = self.vars[vd.name]
            self.error(vd.pos, f"'{vd.name}' is already declared as a {first.kind} at {first.decl.pos}")
            return None
        sym = Symbol(kind, vd.type or TVar(), vd, inferred=vd.type is None)
        self.vars[vd.name] = sym
        return sym

    # ---------- Statements ----------

    def stmt(self, s: Stmt) -> None:
        match s:
            case Block():
                for inner in s.stmts:
                    self.stmt(inner)
            case Assign():
                self.assign(s.target, self.expr(s.value), s.pos)
            case MultiAssign():
                rets = self.call(s.call, multi=True)
                s.call.type = rets  # type: ignore[attr-defined]
                self.typed.append(s.call)
                if isinstance(rets, tuple) and len(rets) != len(s.targets):
                    self.error(s.pos, f"'{s.call.name}' returns {plural(len(rets), 'value')}, "
                                      f"but {plural(len(s.targets), 'variable')} are assigned")
                    rets = ERR
                for i, target in enumerate(s.targets):
                    self.assign(target, rets[i] if isinstance(rets, tuple) else ERR, s.pos)
            case If():
                self.need(s.cond, BOOL, "the condition of 'if'")
                self.stmt(s.then)
                if s.else_:
                    self.stmt(s.else_)
            case While():
                self.need(s.cond, BOOL, "the condition of 'while'")
                if s.invariant:
                    self.need(s.invariant, BOOL, "the predicate of 'invariant'")
                self.stmt(s.body)
            case Assert() | Assume():
                self.need(s.pred, BOOL, f"the predicate of '{type(s).__name__.lower()}'")

    def assign(self, name: str, t: Type, pos: Pos) -> None:
        """Assignment of a value of type t to a variable; an unknown name becomes a new local."""
        sym = self.vars.get(name)
        if sym is None:
            assert self.function is not None
            vd = VarDef(name, None, pos)
            self.function.uses.append(vd)
            sym = self.declare(vd, "local")
            assert sym is not None
        if sym.kind == "parameter":
            self.error(pos, f"cannot assign to parameter '{name}': parameters are read-only")
            return
        if not unify(sym.type, t, pos):
            if sym.inferred:
                self.error(pos, f"cannot assign {show(t)} to '{name}': its type {show(sym.type)} "
                                f"was inferred at {origin(sym.type)}")
            else:
                self.error(pos, f"cannot assign {show(t)} to '{name}' of type {show(sym.type)}")

    # ---------- Expressions ----------

    def need(self, e: Expr, expected: str, what: str) -> Type:
        t = self.expr(e)
        if not unify(t, expected, e.pos):
            note = ""
            if isinstance(e, Var) and (sym := self.vars.get(e.name)) and sym.inferred:
                note = f" ('{e.name}' has type {show(t)}, inferred at {origin(sym.type)})"
            self.error(e.pos, f"{what} must be {expected}, got {show(t)}{note}")
        return t

    def expr(self, e: Expr) -> Type:
        t = self.infer(e)
        e.type = t  # type: ignore[union-attr]  # the annotation: resolved to a string at the end
        self.typed.append(e)
        return t

    def infer(self, e: Expr) -> Type:
        match e:
            case Num():
                return INT
            case BoolLit():
                return BOOL
            case Var():
                sym = self.lookup(e.name, e.pos)
                return sym.type if sym else ERR
            case Index():
                sym = self.lookup(e.array, e.pos)
                if sym and not unify(sym.type, ARR, e.pos):
                    self.error(e.pos, f"'{e.array}' is indexed, so it must be int[], got {show(sym.type)}")
                self.need(e.index, INT, f"the index of '{e.array}'")
                return INT
            case Call():
                return self.call(e, multi=False)
            case FormulaRef():
                item = self.items.get(e.name)
                if item is None:
                    self.error(e.pos, f"unknown formula '{e.name}'")
                elif isinstance(item, Function):
                    self.error(e.pos, f"'{e.name}' is a function, not a formula: a condition is needed here")
                    item = None
                self.args(e.name, e.args, item.params if item else None, e.pos)
                return BOOL
            case Unary():
                t = INT if e.op == "-" else BOOL
                self.need(e.operand, t, f"the operand of '{e.op}'")
                return t
            case Binary():
                operand = BOOL if e.op in LOGIC else INT
                self.need(e.left, operand, f"the left side of '{e.op}'")
                self.need(e.right, operand, f"the right side of '{e.op}'")
                return INT if e.op in ARITH else BOOL
            case Quantifier():
                name = e.var.name
                clash = self.visible(name)
                if clash:
                    self.error(e.var.pos, f"quantifier variable '{name}' clashes with the {clash.kind} "
                                          f"declared at {clash.decl.pos}")
                self.bound.append(Symbol("quantifier variable", e.var.type, e.var))
                self.need(e.body, BOOL, f"the body of '{e.kind}'")
                self.bound.pop()
                return BOOL
            case Update():
                assert isinstance(e.array, Var)  # a[i] = v is the only source of Update
                self.need(e.array, ARR, f"'{e.array.name}' is indexed, so it")
                self.need(e.index, INT, f"the index of '{e.array.name}'")
                self.need(e.value, INT, f"an element of '{e.array.name}'")
                return ARR
        raise AssertionError(e)

    def call(self, e: Call, multi: bool) -> Type:
        """A function call: its return type, or the tuple of return types (multi=True: in `x, y = f(...)`)."""
        if e.name == "length":
            if len(e.args) != 1:
                self.error(e.pos, f"'length' takes 1 argument, got {len(e.args)}")
            for arg in e.args[:1]:
                self.need(arg, ARR, "the argument of 'length'")
            for arg in e.args[1:]:
                self.expr(arg)
            return (INT,) if multi else INT
        item = self.items.get(e.name)
        if item is None:
            self.error(e.pos, f"unknown function '{e.name}'")
        elif isinstance(item, Formula):
            self.error(e.pos, f"'{e.name}' is a formula, not a function: formulas can be used only as "
                              "conditions in predicates")
            item = None
        self.args(e.name, e.args, item.params if item else None, e.pos)
        if item is None:
            return ERR
        rets = tuple(r.type for r in item.returns)
        if multi:
            return rets
        if len(rets) != 1:
            self.error(e.pos, f"'{e.name}' returns {len(rets)} values and cannot be used in an expression: "
                              f"assign them with '{', '.join(r.name for r in item.returns)} = {e.name}(...);'")
            return ERR
        return rets[0]

    def args(self, name: str, args: list[Expr], params: list[VarDef] | None, pos: Pos) -> None:
        if params is not None and len(args) != len(params):
            self.error(pos, f"'{name}' takes {plural(len(params), 'argument')}, got {len(args)}")
        for i, arg in enumerate(args):
            if params is not None and i < len(params):
                self.need(arg, params[i].type, f"argument {i + 1} of '{name}' ({params[i].name})")
            else:
                self.expr(arg)

    # ---------- Names ----------

    def visible(self, name: str) -> Symbol | None:
        for sym in reversed(self.bound):
            if sym.decl.name == name:
                return sym
        sym = self.vars.get(name)
        return sym if sym and sym.kind in self.context.kinds else None

    def lookup(self, name: str, pos: Pos) -> Symbol | None:
        sym = self.visible(name)
        if sym is None:
            hidden = self.vars.get(name)
            if hidden:
                self.error(pos, f"{self.context.rule}, but '{name}' is a {hidden.kind}")
            else:
                self.error(pos, f"unknown variable '{name}'")
        return sym


def kind_of(item: Function | Formula) -> str:
    return "function" if isinstance(item, Function) else "formula"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"
