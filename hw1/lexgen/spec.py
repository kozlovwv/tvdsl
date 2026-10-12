"""Token spec files.

Format, one rule per line:
    NAME [skip] = regex
The regex is the rest of the line after the first '=', with surrounding whitespace stripped
(write a space at the edge of a regex inside a class: [ ]). Lines starting with '#'
and blank lines are ignored. Rule order is priority: of two equally long matches the
earlier rule wins (so keywords go before IDENT).
skip marks a token that is recognised but not emitted (whitespace, comments).
"""

import string
from dataclasses import dataclass
from pathlib import Path

from . import regex

FLAGS = {"skip"}


@dataclass(frozen=True)
class TokenRule:
    name: str
    pattern: str
    regex: regex.Node
    skip: bool = False


class SpecError(ValueError):
    pass


def load_spec(path: str | Path) -> list[TokenRule]:
    return parse_spec(Path(path).read_text(encoding="ascii"), str(path))


def parse_spec(text: str, source: str = "<spec>") -> list[TokenRule]:
    rules: list[TokenRule] = []
    names: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        head, sep, pattern = line.partition("=")
        where = f"{source}:{lineno}"
        if not sep:
            raise SpecError(f"{where}: expected 'NAME [flags] = regex'")
        name, *flags = head.split()
        if not (name[0].isupper() and set(name) <= set(string.ascii_uppercase + string.digits + "_")):
            raise SpecError(f"{where}: bad token name {name!r}")
        if name in names:
            raise SpecError(f"{where}: duplicate token {name}")
        if unknown := set(flags) - FLAGS:
            raise SpecError(f"{where}: unknown flags {sorted(unknown)}")
        pattern = pattern.strip()
        try:
            node = regex.parse(pattern)
        except regex.RegexError as e:
            raise SpecError(f"{where}: {e}") from None
        names.add(name)
        rules.append(TokenRule(name, pattern, node, "skip" in flags))
    if not rules:
        raise SpecError(f"{source}: no token rules")
    return rules
