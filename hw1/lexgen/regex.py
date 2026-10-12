"""Regular expressions of the token spec: syntax and parsing into an AST.

Supported syntax (a subset of Python `re`):
  literals            a  {  }  ,  ;  ...
  escapes             \\n \\t \\r, or a backslash before any metacharacter
  character classes   [a-z_]  [^\\n]   (ranges, negation, escapes inside)
  grouping            ( ... )
  alternation         a|b
  repetition          a*  a+

The alphabet is the 128 ASCII codes plus one symbol OTHER standing for any non-ASCII character.
OTHER cannot be written in a pattern; only negated classes ([^\n]) match it, the same way
they match non-ASCII text in Python `re`. So `//[^\n]*` accepts a comment in Russian, while
non-ASCII anywhere outside such a token still leads to the trap.
"""

from dataclasses import dataclass

ASCII_SIZE = 128
OTHER = 128  # the symbol of every non-ASCII character
ALPHABET_SIZE = 129
ALPHABET = frozenset(range(ALPHABET_SIZE))


def symbol(ch: str) -> int:
    """Alphabet symbol of an input character."""
    return min(ord(ch), OTHER)


@dataclass(frozen=True)
class Chars:
    """Exactly one character from the set."""

    chars: frozenset[int]


@dataclass(frozen=True)
class Concat:
    parts: tuple["Node", ...]


@dataclass(frozen=True)
class Alt:
    options: tuple["Node", ...]


@dataclass(frozen=True)
class Star:
    inner: "Node"


@dataclass(frozen=True)
class Epsilon:
    pass


type Node = Chars | Concat | Alt | Star | Epsilon


class RegexError(ValueError):
    def __init__(self, message: str, pattern: str, pos: int) -> None:
        super().__init__(f"{message} at position {pos} in /{pattern}/")
        self.pos = pos


SIMPLE_ESCAPES = {"n": 10, "t": 9, "r": 13}


def parse(pattern: str) -> Node:
    return _Parser(pattern).parse()


class _Parser:
    """Recursive descent over:  alt = concat {"|" concat};  concat = {repeat};
    repeat = atom {"*" | "+"};  atom = "(" alt ")" | class | escape | char."""

    def __init__(self, pattern: str) -> None:
        self.p = pattern
        self.i = 0

    def error(self, message: str, pos: int | None = None) -> RegexError:
        return RegexError(message, self.p, self.i if pos is None else pos)

    def peek(self) -> str | None:
        return self.p[self.i] if self.i < len(self.p) else None

    def take(self) -> str:
        c = self.p[self.i]
        self.i += 1
        return c

    def parse(self) -> Node:
        node = self.alt()
        if self.i < len(self.p):
            raise self.error(f"unbalanced {self.p[self.i]!r}")
        return node

    def alt(self) -> Node:
        options = [self.concat()]
        while self.peek() == "|":
            self.i += 1
            options.append(self.concat())
        return options[0] if len(options) == 1 else Alt(tuple(options))

    def concat(self) -> Node:
        parts = []
        while (c := self.peek()) is not None and c not in "|)":
            parts.append(self.repeat())
        if not parts:
            return Epsilon()
        return parts[0] if len(parts) == 1 else Concat(tuple(parts))

    def repeat(self) -> Node:
        node = self.atom()
        while (c := self.peek()) is not None and c in "*+":
            self.i += 1
            node = Star(node) if c == "*" else Concat((node, Star(node)))
        return node

    def atom(self) -> Node:
        start = self.i
        c = self.take()
        match c:
            case "(":
                node = self.alt()
                if self.peek() != ")":
                    raise self.error("missing ')'", start)
                self.i += 1
                return node
            case "[":
                return Chars(self.char_class(start))
            case "\\":
                return Chars(frozenset({self.escape()}))
            case "*" | "+":
                raise self.error(f"nothing to repeat before {c!r}", start)
            case "?" | ".":
                raise self.error(f"unsupported {c!r}; escape it to match literally", start)
            case "]":
                raise self.error("unbalanced ']'", start)
            case _:
                return Chars(frozenset({self.ascii(c, start)}))

    def char_class(self, start: int) -> frozenset[int]:
        negate = self.peek() == "^"
        if negate:
            self.i += 1
        chars: set[int] = set()
        while True:
            c = self.peek()
            if c is None:
                raise self.error("missing ']'", start)
            if c == "]":
                self.i += 1
                break
            range_start = self.i
            lo = self.class_char()
            # '-' is a range operator unless it is the last char of the class
            if self.peek() == "-" and self.i + 1 < len(self.p) and self.p[self.i + 1] != "]":
                self.i += 1
                hi = self.class_char()
                if hi < lo:
                    raise self.error("invalid range", range_start)
                chars.update(range(lo, hi + 1))
            else:
                chars.add(lo)
        result = ALPHABET - chars if negate else frozenset(chars)
        if not result:
            raise self.error("empty character class", start)
        return result

    def class_char(self) -> int:
        pos = self.i
        c = self.take()
        return self.escape() if c == "\\" else self.ascii(c, pos)

    def escape(self) -> int:
        """Called right after the backslash has been consumed."""
        start = self.i - 1
        if self.i >= len(self.p):
            raise self.error("dangling '\\'", start)
        c = self.take()
        if c in SIMPLE_ESCAPES:
            return SIMPLE_ESCAPES[c]
        if c.isalnum():
            raise self.error(f"unknown escape '\\{c}'", start)
        return self.ascii(c, start)

    def ascii(self, c: str, pos: int) -> int:
        code = ord(c)
        if code >= ASCII_SIZE:
            raise self.error(f"non-ASCII character {c!r}", pos)
        return code
