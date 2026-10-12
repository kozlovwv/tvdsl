"""Thompson construction: regex AST -> epsilon-NFA."""

from collections.abc import Sequence
from dataclasses import dataclass

from .regex import Alt, Chars, Concat, Epsilon, Node, Star


@dataclass
class NFA:
    start: int
    eps: list[list[int]]  # eps[s]: targets of epsilon edges from s
    edges: list[list[tuple[frozenset[int], int]]]  # edges[s]: (char set, target)
    accepting: dict[int, int]  # final state -> index of the token rule

    @property
    def size(self) -> int:
        return len(self.eps)


class _Builder:
    def __init__(self) -> None:
        self.eps: list[list[int]] = []
        self.edges: list[list[tuple[frozenset[int], int]]] = []

    def new_state(self) -> int:
        self.eps.append([])
        self.edges.append([])
        return len(self.eps) - 1

    def build(self, node: Node) -> tuple[int, int]:
        """Builds a fragment for `node`, returns its (start, final) states."""
        match node:
            case Chars(chars):
                s, f = self.new_state(), self.new_state()
                self.edges[s].append((chars, f))
                return s, f
            case Epsilon():
                s, f = self.new_state(), self.new_state()
                self.eps[s].append(f)
                return s, f
            case Concat(parts):
                s, f = self.build(parts[0])
                for part in parts[1:]:
                    ps, pf = self.build(part)
                    self.eps[f].append(ps)
                    f = pf
                return s, f
            case Alt(options):
                s, f = self.new_state(), self.new_state()
                for option in options:
                    os, of = self.build(option)
                    self.eps[s].append(os)
                    self.eps[of].append(f)
                return s, f
            case Star(inner):
                s, f = self.new_state(), self.new_state()
                ins, inf = self.build(inner)
                self.eps[s] += [ins, f]
                self.eps[inf] += [ins, f]
                return s, f


def build_nfa(regexes: Sequence[Node]) -> NFA:
    """One NFA for all token rules: a common start with epsilon edges to each rule's fragment.
    The final state of rule i is labelled with i."""
    builder = _Builder()
    start = builder.new_state()
    accepting = {}
    for index, node in enumerate(regexes):
        s, f = builder.build(node)
        builder.eps[start].append(s)
        accepting[f] = index
    return NFA(start, builder.eps, builder.edges, accepting)
