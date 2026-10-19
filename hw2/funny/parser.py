"""LL(1) recursive-descent parser for Funny (grammar.ebnf): tokens -> AST.

One method per nonterminal; every choice is made by the next token (`self.tok`). Expressions, conditions
and predicates share one grammar; each node gets a sort (NUM or BOOL) and operators check the sorts of
their operands (see grammar.ebnf).

Error recovery (panic mode): a syntax error raises ParseError, which is caught at the statement level
(inside a block) and at the module level (around a function or formula). The error is recorded, then
tokens are skipped up to a synchronising token, and parsing goes on:
  statement: up to and including ';', or up to '}' / a statement keyword / EOF;
  item:      past the end of the current definition (balanced braces), up to the next definition.
Every skip consumes at least one token, so the parser always terminates.
"""

from .ast import (Assert, Assign, Assume, Binary, Block, BoolLit, Call, Expr, Formula, FormulaRef, Function,
                  If, Index, MultiAssign, Num, Program, Quantifier, Stmt, Unary, Update, Var, VarDef, While)
from .lexer import Diagnostic, Pos, Table, Token, tokenize

NUM, BOOL = "num", "bool"
SORT_NAME = {NUM: "a number expression", BOOL: "a logical expression"}

# How tokens are named in messages.
SPELLING = {
    "LPAREN": "(", "RPAREN": ")", "LBRACKET": "[", "RBRACKET": "]", "LBRACE": "{", "RBRACE": "}",
    "COMMA": ",", "SEMI": ";", "COLON": ":", "PIPE": "|", "ASSIGN": "=", "IMPLIES": "=>", "ARROW": "->",
    "EQ": "==", "NE": "!=", "LT": "<", "LE": "<=", "GT": ">", "GE": ">=",
    "PLUS": "+", "MINUS": "-", "STAR": "*", "SLASH": "/",
}
REL_OPS = {"EQ", "NE", "LT", "LE", "GT", "GE"}
STATEMENT_START = {"LBRACE", "KW_IF", "KW_WHILE", "KW_ASSERT", "KW_ASSUME"}


def spell(kind: str) -> str:
    if kind in SPELLING:
        return f"'{SPELLING[kind]}'"
    if kind.startswith("KW_"):
        return f"'{kind[3:].lower()}'"
    return {"IDENT": "a name", "INT": "a number", "EOF": "end of input"}[kind]


def describe(tok: Token) -> str:
    if tok.kind == "EOF":
        return "end of input"
    if tok.kind in ("IDENT", "INT"):
        return f"{'name' if tok.kind == 'IDENT' else 'number'} '{tok.text}'"
    return f"'{tok.text}'"


class ParseError(Exception):
    def __init__(self, pos: Pos, message: str) -> None:
        super().__init__(message)
        self.diag = Diagnostic(pos, message)


def parse(text: str, table: Table) -> tuple[Program | None, list[Diagnostic]]:
    """The AST and no errors, or None and the errors (lexical errors stop before parsing)."""
    tokens, errors = tokenize(table, text)
    if errors:
        return None, errors
    parser = Parser(tokens)
    program = parser.program()
    return (None, parser.errors) if parser.errors else (program, [])


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0
        self.errors: list[Diagnostic] = []
        self.in_predicate = False  # quantifiers and formula references are allowed only in predicates

    # ---------- Token helpers ----------

    @property
    def tok(self) -> Token:
        return self.tokens[self.i]

    def at(self, *kinds: str) -> bool:
        return self.tok.kind in kinds

    def advance(self) -> Token:
        tok = self.tok
        if tok.kind != "EOF":
            self.i += 1
        return tok

    def expect(self, kind: str, context: str = "") -> Token:
        if not self.at(kind):
            raise self.error(f"expected {spell(kind)}{' ' + context if context else ''}, got {describe(self.tok)}")
        return self.advance()

    def error(self, message: str, pos: Pos | None = None) -> ParseError:
        return ParseError(pos or self.tok.pos, message)

    # ---------- Module ----------

    def program(self) -> Program:
        items: list[Function | Formula] = []
        if self.at("EOF"):
            self.errors.append(Diagnostic(self.tok.pos, "empty program: expected a function or formula definition"))
        while not self.at("EOF"):
            try:
                items.append(self.item())
            except ParseError as e:
                self.errors.append(e.diag)
                self.sync_item()
        return Program(items)

    def item(self) -> Function | Formula:
        if self.at("KW_FUNCTION"):
            self.advance()
        name = self.expect("IDENT", "of a function or formula")
        self.expect("LPAREN", f"after the name '{name.text}'")
        params = [] if self.at("RPAREN") else self.var_defs()
        self.expect("RPAREN", "after the parameters")

        if self.at("IMPLIES"):  # formula
            self.advance()
            body = self.predicate(f"the formula '{name.text}'")
            if self.at("SEMI"):
                self.advance()
            return Formula(name.text, params, body, name.pos)

        if not self.at("KW_REQUIRES", "KW_RETURNS"):
            raise self.error(f"expected 'requires', 'returns' or '=>' after the parameters of '{name.text}', "
                             f"got {describe(self.tok)}")
        requires = None
        if self.at("KW_REQUIRES"):
            self.advance()
            requires = self.predicate("'requires'")
        self.expect("KW_RETURNS", f"in the definition of '{name.text}'")
        returns = self.var_defs()
        ensures = None
        if self.at("KW_ENSURES"):
            self.advance()
            ensures = self.predicate("'ensures'")
        uses = []
        if self.at("KW_USES"):
            self.advance()
            uses.append(self.local_def())
            while self.at("COMMA"):
                self.advance()
                uses.append(self.local_def())
        body = self.statement()
        return Function(name.text, params, requires, returns, ensures, uses, body, name.pos)

    def var_defs(self) -> list[VarDef]:
        defs = [self.var_def()]
        while self.at("COMMA"):
            self.advance()
            defs.append(self.var_def())
        return defs

    def var_def(self) -> VarDef:
        name = self.expect("IDENT", "of a variable")
        self.expect("COLON", f"and a type after '{name.text}'")
        return VarDef(name.text, self.type_(), name.pos)

    def local_def(self) -> VarDef:
        name = self.expect("IDENT", "of a local variable")
        if not self.at("COLON"):
            return VarDef(name.text, None, name.pos)
        self.advance()
        return VarDef(name.text, self.type_(), name.pos)

    def type_(self) -> str:
        self.expect("KW_INT", "(a type: int or int[])")
        if not self.at("LBRACKET"):
            return "int"
        self.advance()
        self.expect("RBRACKET", "in 'int[]'")
        return "int[]"

    # ---------- Statements ----------

    def statement(self) -> Stmt:
        tok = self.tok
        match tok.kind:
            case "LBRACE":
                return self.block()
            case "KW_IF":
                self.advance()
                self.expect("LPAREN", "after 'if'")
                cond = self.condition("'if'")
                then = self.statement()
                else_ = None
                if self.at("KW_ELSE"):  # dangling else: binds to the nearest if
                    self.advance()
                    else_ = self.statement()
                return If(cond, then, else_, tok.pos)
            case "KW_WHILE":
                self.advance()
                self.expect("LPAREN", "after 'while'")
                cond = self.condition("'while'")
                invariant = None
                if self.at("KW_INVARIANT"):
                    self.advance()
                    invariant = self.predicate("'invariant'")
                return While(cond, invariant, self.statement(), tok.pos)
            case "KW_ASSERT" | "KW_ASSUME":
                self.advance()
                pred = self.predicate(f"'{tok.text}'")
                self.expect("SEMI", f"after the predicate of '{tok.text}'")
                return Assert(pred, tok.pos) if tok.kind == "KW_ASSERT" else Assume(pred, tok.pos)
            case "IDENT":
                return self.assignment()
        raise self.error(f"expected a statement, got {describe(tok)}")

    def block(self) -> Block:
        lbrace = self.expect("LBRACE")
        stmts: list[Stmt] = []
        while not self.at("RBRACE"):
            if self.at("EOF"):
                raise self.error(f"missing '}}' to close the block opened at {lbrace.pos}")
            try:
                stmts.append(self.statement())
            except ParseError as e:
                self.errors.append(e.diag)
                self.sync_statement()
        self.advance()
        return Block(stmts, lbrace.pos)

    def assignment(self) -> Stmt:
        name = self.advance()
        if self.at("ASSIGN"):  # x = e;
            self.advance()
            value = self.expr("the assigned value")
            self.expect("SEMI", "after the assignment")
            return Assign(name.text, value, name.pos)
        if self.at("LBRACKET"):  # a[i] = e;  ->  a = Update(a, i, e)
            self.advance()
            index = self.expr("the index")
            self.expect("RBRACKET", "after the index")
            self.expect("ASSIGN", f"after '{name.text}[...]'")
            value = self.expr("the assigned value")
            self.expect("SEMI", "after the assignment")
            return Assign(name.text, Update(Var(name.text, name.pos), index, value, name.pos), name.pos)
        if self.at("COMMA"):  # x, y = f(...);
            targets = [name.text]
            while self.at("COMMA"):
                self.advance()
                targets.append(self.expect("IDENT", "of a variable in a multiple assignment").text)
            self.expect("ASSIGN", "after the variables of a multiple assignment")
            value = self.expr("the right side of a multiple assignment")
            if not isinstance(value, Call):
                raise self.error("the right side of a multiple assignment must be a function call", value.pos)
            self.expect("SEMI", "after the assignment")
            return MultiAssign(targets, value, name.pos)
        raise self.error(f"expected '=', '[' or ',' after the name '{name.text}', got {describe(self.tok)}")

    # ---------- Expressions ----------

    def condition(self, owner: str) -> Expr:
        """if/while condition and the closing ')': a logical expression without quantifiers and formula
        references. The ')' is checked before the sort, so 'if (a = b)' reports the unexpected '='."""
        saved, self.in_predicate = self.in_predicate, False
        try:
            cond = self.bool_expr()
            self.expect("RPAREN", f"after the condition of {owner}")
            return self.need(cond, BOOL, f"the condition of {owner}")
        finally:
            self.in_predicate = saved

    def predicate(self, owner: str) -> Expr:
        saved, self.in_predicate = self.in_predicate, True
        try:
            return self.need(self.bool_expr(), BOOL, f"the predicate of {owner}")
        finally:
            self.in_predicate = saved

    def expr(self, what: str) -> Expr:
        return self.need(self.bool_expr(), NUM, what)

    def bool_expr(self) -> Expr:
        return self.implies()

    def implies(self) -> Expr:
        left = self.or_expr()
        if not self.at("ARROW"):
            return left
        op = self.advance()
        right = self.implies()  # right-associative: a -> b -> c = a -> (b -> c)
        return Binary("->", self.need(left, BOOL, "the left side of '->'"),
                      self.need(right, BOOL, "the right side of '->'"), op.pos)

    def or_expr(self) -> Expr:
        left = self.and_expr()
        while self.at("KW_OR"):
            op = self.advance()
            right = self.and_expr()
            left = Binary("or", self.need(left, BOOL, "an operand of 'or'"),
                          self.need(right, BOOL, "an operand of 'or'"), op.pos)
        return left

    def and_expr(self) -> Expr:
        left = self.not_expr()
        while self.at("KW_AND"):
            op = self.advance()
            right = self.not_expr()
            left = Binary("and", self.need(left, BOOL, "an operand of 'and'"),
                          self.need(right, BOOL, "an operand of 'and'"), op.pos)
        return left

    def not_expr(self) -> Expr:
        if not self.at("KW_NOT"):
            return self.comparison()
        op = self.advance()
        return Unary("not", self.need(self.not_expr(), BOOL, "the operand of 'not'"), op.pos)

    def comparison(self) -> Expr:
        left = self.sum()
        if not self.at(*REL_OPS):
            return left
        op = self.advance()
        right = self.sum()
        node = Binary(op.text, self.need(left, NUM, f"the left side of '{op.text}'"),
                      self.need(right, NUM, f"the right side of '{op.text}'"), op.pos)
        if self.at(*REL_OPS):
            raise self.error(f"comparisons cannot be chained: write 'a {op.text} b and b {self.tok.text} c'")
        return node

    def sum(self) -> Expr:
        left = self.product()
        while self.at("PLUS", "MINUS"):
            op = self.advance()
            right = self.product()
            left = Binary(op.text, self.need(left, NUM, f"an operand of '{op.text}'"),
                          self.need(right, NUM, f"an operand of '{op.text}'"), op.pos)
        return left

    def product(self) -> Expr:
        left = self.unary()
        while self.at("STAR", "SLASH"):
            op = self.advance()
            right = self.unary()
            left = Binary(op.text, self.need(left, NUM, f"an operand of '{op.text}'"),
                          self.need(right, NUM, f"an operand of '{op.text}'"), op.pos)
        return left

    def unary(self) -> Expr:
        if not self.at("MINUS"):
            return self.primary()
        op = self.advance()
        return Unary("-", self.need(self.unary(), NUM, "the operand of unary '-'"), op.pos)

    def primary(self) -> Expr:
        tok = self.tok
        match tok.kind:
            case "INT":
                self.advance()
                return Num(int(tok.text), tok.pos)
            case "KW_TRUE" | "KW_FALSE":
                self.advance()
                return BoolLit(tok.kind == "KW_TRUE", tok.pos)
            case "LPAREN":
                self.advance()
                inner = self.bool_expr()
                self.expect("RPAREN", f"to close '(' at {tok.pos}")
                return inner
            case "KW_FORALL" | "KW_EXISTS":
                return self.quantifier()
            case "KW_LENGTH":
                self.advance()
                return Call("length", self.call_args(tok), tok.pos)
            case "IDENT":
                self.advance()
                if self.at("LPAREN"):
                    return Call(tok.text, self.call_args(tok), tok.pos)
                if self.at("LBRACKET"):
                    self.advance()
                    index = self.expr("the index")
                    self.expect("RBRACKET", f"to close '[' after '{tok.text}'")
                    return Index(tok.text, index, tok.pos)
                return Var(tok.text, tok.pos)
        raise self.error(f"expected an expression, got {describe(tok)}")

    def call_args(self, name: Token) -> list[Expr]:
        self.expect("LPAREN", f"after '{name.text}'")
        args: list[Expr] = []
        if not self.at("RPAREN"):
            args.append(self.expr(f"an argument of '{name.text}'"))
            while self.at("COMMA"):
                self.advance()
                args.append(self.expr(f"an argument of '{name.text}'"))
        self.expect("RPAREN", f"to close the arguments of '{name.text}'")
        return args

    def quantifier(self) -> Quantifier:
        kw = self.advance()
        if not self.in_predicate:
            raise self.error(f"'{kw.text}' is allowed only in predicates "
                             "(requires, ensures, invariant, assert, assume, formulas)", kw.pos)
        self.expect("LPAREN", f"after '{kw.text}'")
        var = self.var_def()
        self.expect("PIPE", f"after the variable of '{kw.text}'")
        body = self.need(self.bool_expr(), BOOL, f"the body of '{kw.text}'")
        self.expect("RPAREN", f"to close '{kw.text}'")
        return Quantifier(kw.text, var, body, kw.pos)

    # ---------- Sorts ----------

    def need(self, node: Expr, sort: str, what: str) -> Expr:
        """Checks that `node` has the sort required at its place. A call f(...) gets its sort from the place:
        a function call where a number is needed, a formula reference where a truth value is needed."""
        actual = sort_of(node)
        if actual == "call":
            if sort == NUM:
                return node
            assert isinstance(node, Call)
            if not self.in_predicate:
                raise self.error(f"{what} must be {SORT_NAME[BOOL]}, got a call of '{node.name}' "
                                 "(formula references are allowed only in predicates)", node.pos)
            return FormulaRef(node.name, node.args, node.pos)
        if actual != sort:
            raise self.error(f"{what} must be {SORT_NAME[sort]}, got {SORT_NAME[actual]}", node.pos)
        return node

    # ---------- Panic-mode recovery ----------

    def sync_statement(self) -> None:
        """Skips to the end of the broken statement: past ';', or up to '}', a statement keyword or EOF.
        Stopping without consuming is safe: the block loop stops at '}' and EOF, and a statement keyword
        is always consumed by the next statement() - an error can only happen at a token that cannot
        start a statement."""
        while not self.at("EOF", "RBRACE", *STATEMENT_START):
            if self.at("SEMI"):
                self.advance()
                return
            self.advance()

    def sync_item(self) -> None:
        """Skips the rest of the broken definition: tokens up to the next name that starts a line-level
        definition - a name or 'function' right after '}' or ';' outside of any braces."""
        start = self.i
        depth = 0
        while not self.at("EOF"):
            prev = self.tokens[self.i - 1].kind if self.i > 0 else None
            if self.i > start and depth == 0 and self.at("IDENT", "KW_FUNCTION") and prev in ("RBRACE", "SEMI"):
                return
            if self.at("LBRACE"):
                depth += 1
            elif self.at("RBRACE"):
                depth = max(0, depth - 1)
            self.advance()


def sort_of(node: Expr) -> str:
    match node:
        case Call(name="length"):
            return NUM
        case Call():
            return "call"
        case Num() | Var() | Index() | Update():
            return NUM
        case Unary(op="-"):
            return NUM
        case Binary(op="+" | "-" | "*" | "/"):
            return NUM
        case _:
            return BOOL
