"""Lexer: runs the DFA table exported by HW1 (hw1/out/dfa.json) over the text.

Longest match: from the current position the DFA runs until the trap, and the longest accepted prefix
becomes the token; ties between rules are already resolved inside the table by rule priority.
Skip tokens (WS, COMMENT) are dropped, error tokens (BAD_NUMBER) are reported. Every token gets
its line and column (both from 1; a tab counts as one column).
"""

import json
from dataclasses import dataclass
from pathlib import Path

FORMAT = "funny-lexer-dfa/1"
OTHER = 128  # table column of every non-ASCII character
DEFAULT_TABLE = Path(__file__).resolve().parents[2] / "hw1" / "out" / "dfa.json"


@dataclass(frozen=True)
class Pos:
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


@dataclass(frozen=True)
class Token:
    kind: str  # token name from hw1/tokens.spec, or EOF
    text: str
    pos: Pos


@dataclass(frozen=True)
class Diagnostic:
    pos: Pos
    message: str

    def __str__(self) -> str:
        return f"{self.pos}: {self.message}"


@dataclass(frozen=True)
class Table:
    start: int
    trap: int
    accept: list[str | None]
    transitions: list[list[int]]
    skip: frozenset[str]
    errors: frozenset[str]

    @classmethod
    def load(cls, path: str | Path = DEFAULT_TABLE) -> "Table":
        data = json.loads(Path(path).read_text(encoding="ascii"))
        if data.get("format") != FORMAT:
            raise ValueError(f"{path}: unsupported table format {data.get('format')!r}")
        return cls(data["start"], data["trap"], data["accept"], data["transitions"],
                   frozenset(data["skip"]), frozenset(data["errors"]))

    def step(self, state: int, ch: str) -> int:
        return self.transitions[state][min(ord(ch), OTHER)]


def tokenize(table: Table, text: str) -> tuple[list[Token], list[Diagnostic]]:
    """All tokens followed by EOF, and the lexical errors. After an error the lexer skips the bad
    character (or the whole malformed token) and goes on, so all errors are reported at once."""
    tokens: list[Token] = []
    errors: list[Diagnostic] = []
    pos, line, col = 0, 1, 1
    while pos < len(text):
        state = table.start
        last: tuple[int, str] | None = None  # (end of the longest accepted prefix, token)
        i = pos
        while i < len(text):
            state = table.step(state, text[i])
            if state == table.trap:
                break
            i += 1
            if (kind := table.accept[state]) is not None:
                last = (i, kind)

        here = Pos(line, col)
        if last is None:
            ch = text[pos]
            what = "non-ASCII character" if ord(ch) >= OTHER else "unexpected character"
            errors.append(Diagnostic(here, f"{what} {ch!r}"))
            end = pos + 1
        else:
            end, kind = last
            lexeme = text[pos:end]
            if kind in table.errors:
                errors.append(Diagnostic(here, f"malformed number {lexeme!r}"))
            elif kind not in table.skip:
                tokens.append(Token(kind, lexeme, here))

        lexeme = text[pos:end]
        if (newlines := lexeme.count("\n")) > 0:
            line += newlines
            col = len(lexeme) - lexeme.rfind("\n")
        else:
            col += len(lexeme)
        pos = end
    tokens.append(Token("EOF", "", Pos(line, col)))
    return tokens, errors
