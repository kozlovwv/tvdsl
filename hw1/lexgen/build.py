"""The whole pipeline: spec -> NFA -> DFA -> minimal DFA -> table."""

from dataclasses import dataclass

from .dfa import DFA, determinize, minimize
from .nfa import NFA, build_nfa
from .spec import TokenRule
from .table import LexTable


@dataclass
class Build:
    rules: list[TokenRule]
    nfa: NFA
    dfa: DFA
    min_dfa: DFA

    @property
    def table(self) -> LexTable:
        return LexTable.from_dfa(self.min_dfa, self.rules)

    @property
    def unminimized_table(self) -> LexTable:
        return LexTable.from_dfa(self.dfa, self.rules)


def build(rules: list[TokenRule]) -> Build:
    nfa = build_nfa([r.regex for r in rules])
    dfa = determinize(nfa)
    return Build(rules, nfa, dfa, minimize(dfa))
