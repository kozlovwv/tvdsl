"""Transition table: the build output that the lexer runs on.

It is what gets serialized to JSON for the project lexer (T0).
Columns are alphabet symbols: ASCII codes 0..127 and 128 for any non-ASCII character.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dfa import DFA
from .regex import symbol
from .spec import TokenRule

FORMAT = "funny-lexer-dfa/1"


@dataclass(frozen=True)
class LexTable:
    start: int
    trap: int
    transitions: list[list[int]]  # [state][symbol] -> state
    accept: list[str | None]  # token name accepted in the state
    skip: frozenset[str]

    def step(self, state: int, ch: str) -> int:
        return self.transitions[state][symbol(ch)]

    @classmethod
    def from_dfa(cls, dfa: DFA, rules: list[TokenRule]) -> "LexTable":
        return cls(
            start=dfa.start,
            trap=dfa.trap,
            transitions=dfa.trans,
            accept=[None if a is None else rules[a].name for a in dfa.accept],
            skip=frozenset(r.name for r in rules if r.skip),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "alphabet": "column c for ASCII code c; column 128 for any non-ASCII char",
            "start": self.start,
            "trap": self.trap,
            "skip": sorted(self.skip),
            "accept": self.accept,
            "transitions": self.transitions,
        }

    def save(self, path: str | Path) -> None:
        # Every list on one line and one table row per line: readable in a diff, still valid JSON.
        data = self.to_json()
        rows = ",\n    ".join(json.dumps(row) for row in data.pop("transitions"))
        fields = "".join(f"  {json.dumps(key)}: {json.dumps(value)},\n" for key, value in data.items())
        Path(path).write_text(f'{{\n{fields}  "transitions": [\n    {rows}\n  ]\n}}\n', encoding="ascii")

