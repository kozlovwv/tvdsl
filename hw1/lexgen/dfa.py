"""Subset construction (NFA -> DFA) and Hopcroft minimization.

DFAs here are complete: every state has a transition on each alphabet symbol (128 ASCII
codes + OTHER for non-ASCII), missing ones go to an explicit trap (dead) state. Accepting states carry the index
of the token rule they accept; lower index = higher priority.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from .nfa import NFA
from .regex import ALPHABET_SIZE


@dataclass
class DFA:
    start: int
    trap: int
    trans: list[list[int]]  # trans[state][symbol]
    accept: list[int | None]  # rule index accepted in the state, None if not accepting

    @property
    def size(self) -> int:
        return len(self.trans)


def determinize(nfa: NFA) -> DFA:
    closures: dict[frozenset[int], frozenset[int]] = {}

    def closure(states: Iterable[int]) -> frozenset[int]:
        key = frozenset(states)
        if key not in closures:
            seen = set(key)
            stack = list(key)
            while stack:
                for t in nfa.eps[stack.pop()]:
                    if t not in seen:
                        seen.add(t)
                        stack.append(t)
            closures[key] = frozenset(seen)
        return closures[key]

    start = closure([nfa.start])
    index = {start: 0}
    sets = [start]
    trans: list[list[int]] = []
    i = 0
    while i < len(sets):
        targets: list[set[int]] = [set() for _ in range(ALPHABET_SIZE)]
        for s in sets[i]:
            for chars, t in nfa.edges[s]:
                for c in chars:
                    targets[c].add(t)
        row = []
        for c in range(ALPHABET_SIZE):
            nxt = closure(targets[c])  # the empty set is the trap state
            if nxt not in index:
                index[nxt] = len(sets)
                sets.append(nxt)
            row.append(index[nxt])
        trans.append(row)
        i += 1

    trap = index.get(frozenset())
    if trap is None:  # every code leads somewhere: add an unreachable trap for uniformity
        trap = len(sets)
        sets.append(frozenset())
        trans.append([trap] * ALPHABET_SIZE)

    accept = []
    for states in sets:
        labels = [nfa.accepting[s] for s in states if s in nfa.accepting]
        accept.append(min(labels) if labels else None)
    return DFA(0, trap, trans, accept)


def minimize(dfa: DFA) -> DFA:
    """Hopcroft's partition refinement.

    The initial partition groups states by the accepted rule, not just accepting/non-accepting:
    otherwise e.g. IDENT and keyword states would be merged.
    """
    inverse: list[list[list[int]]] = [[[] for _ in range(dfa.size)] for _ in range(ALPHABET_SIZE)]
    for s, row in enumerate(dfa.trans):
        for c, t in enumerate(row):
            inverse[c][t].append(s)

    groups: dict[int | None, set[int]] = {}
    for s, label in enumerate(dfa.accept):
        groups.setdefault(label, set()).add(s)
    partition = [frozenset(g) for g in groups.values()]
    # With more than two initial blocks, putting all of them into the worklist keeps it correct.
    worklist = set(partition)

    while worklist:
        splitter = worklist.pop()
        for c in range(ALPHABET_SIZE):
            preds: set[int] = set()
            for t in splitter:
                preds.update(inverse[c][t])
            if not preds:
                continue
            refined = []
            for block in partition:
                inside = block & preds
                if not inside or len(inside) == len(block):
                    refined.append(block)
                    continue
                outside = block - inside
                refined += [inside, outside]
                if block in worklist:
                    worklist.remove(block)
                    worklist |= {inside, outside}
                else:
                    worklist.add(min(inside, outside, key=len))
            partition = refined

    # Renumber blocks in BFS order from the start so the output is deterministic.
    block_of = {s: b for b, block in enumerate(partition) for s in block}
    representative = [next(iter(block)) for block in partition]
    order = {block_of[dfa.start]: 0}
    queue = [block_of[dfa.start]]
    for b in queue:
        for t in dfa.trans[representative[b]]:
            if block_of[t] not in order:
                order[block_of[t]] = len(order)
                queue.append(block_of[t])
    if block_of[dfa.trap] not in order:
        order[block_of[dfa.trap]] = len(order)
        queue.append(block_of[dfa.trap])

    trans = [[order[block_of[t]] for t in dfa.trans[representative[b]]] for b in queue]
    accept = [dfa.accept[representative[b]] for b in queue]
    return DFA(0, order[block_of[dfa.trap]], trans, accept)

