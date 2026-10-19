"""Running text through the DFA table.

classify: the whole text as one token.
tokenize: the text split into tokens by longest match; ties are already resolved in the table
by rule priority. Skip tokens (whitespace, comments) are recognised but dropped;
error tokens (01) are recognised and reported as a lexical error.
"""

from .table import LexTable


class LexError(Exception):
    def __init__(self, message: str, pos: int) -> None:
        super().__init__(f"offset {pos}: {message}")
        self.pos = pos


def classify(table: LexTable, text: str) -> str:
    """The accepted token, TRAP (no token starts like this) or REJECT (an unfinished
    prefix of a token, e.g. '' or '!')."""
    state = table.start
    for ch in text:
        state = table.step(state, ch)
        if state == table.trap:
            return "TRAP"
    return table.accept[state] or "REJECT"


def tokenize(table: LexTable, text: str) -> list[tuple[str, str]]:
    """(token, lexeme) pairs; raises LexError where no token can be read."""
    tokens = []
    pos = 0
    while pos < len(text):
        # Run the DFA from pos until the trap, remembering the last accepting point.
        state = table.start
        last: tuple[int, str] | None = None
        i = pos
        while i < len(text):
            state = table.step(state, text[i])
            if state == table.trap:
                break
            i += 1
            if (kind := table.accept[state]) is not None:
                last = (i, kind)
        if last is None:
            raise LexError(f"no token starts with {text[pos]!r}", pos)
        end, kind = last
        if kind in table.errors:
            raise LexError(f"malformed token {text[pos:end]!r} ({kind})", pos)
        if kind not in table.skip:
            tokens.append((kind, text[pos:end]))
        pos = end
    return tokens
