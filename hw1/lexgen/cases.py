"""Test cases file (tests/cases.tsv) and running them through the DFA table.

Tab-separated lines:  kind <TAB> input <TAB> expected [<TAB> comment]
  match  input  TOKEN | TRAP | REJECT     the whole input as one token
  lex    input  TOK TOK ... | ERROR n     the input split into tokens, or the offset of the
                                          first character no token can start with
The input uses Python escapes (\\n, \\t, \\r, \\u00e9, \\x23); the file itself is pure ASCII.
An empty expected field of a lex case means no tokens. Lines starting with '#' are comments.
"""

from dataclasses import dataclass
from pathlib import Path

from .lexer import LexError, classify, tokenize
from .table import LexTable


@dataclass(frozen=True)
class Case:
    lineno: int
    kind: str
    input: str
    expected: str
    comment: str = ""


def load_cases(path: str | Path) -> list[Case]:
    cases = []
    for lineno, line in enumerate(Path(path).read_text(encoding="ascii").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) not in (3, 4) or fields[0] not in ("match", "lex"):
            raise ValueError(f"{path}:{lineno}: expected 'match|lex<TAB>input<TAB>expected[<TAB>comment]'")
        text = fields[1].encode("ascii").decode("unicode_escape")
        cases.append(Case(lineno, fields[0], text, " ".join(fields[2].split()), *fields[3:]))
    return cases


def run_case(table: LexTable, case: Case) -> str:
    """The actual result, written the same way as Case.expected."""
    if case.kind == "match":
        return classify(table, case.input)
    try:
        return " ".join(kind for kind, _ in tokenize(table, case.input))
    except LexError as e:
        return f"ERROR {e.pos}"
