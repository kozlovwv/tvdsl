"""Fixed-point liveness, interference graph and deterministic greedy coloring."""


def liveness(f):
    uses, defs = {}, {}
    for b in f.blocks:
        used, defined = set(), set()
        for i in b.code:
            used |= i.uses() - defined
            defined.update(i.dest)
        uses[b.label], defs[b.label] = used, defined
    inside = {b.label: set() for b in f.blocks}
    outside = {b.label: set() for b in f.blocks}
    changed = True
    while changed:
        changed = False
        for b in reversed(f.blocks):
            out = set().union(*(inside[s] for s in b.successors()))
            inn = uses[b.label] | (out - defs[b.label])
            if inn != inside[b.label] or out != outside[b.label]:
                inside[b.label], outside[b.label] = inn, out
                changed = True
    return inside, outside


def allocate(f):
    inside, outside = liveness(f)
    graph = {}

    def clique(names):
        for x in names:
            graph.setdefault(x, set()).update(names - {x})

    for b in f.blocks:
        live = set(outside[b.label])
        clique(live)
        for i in reversed(b.code):
            # Results simultaneously exist, even when one of them is unused.
            clique(live | set(i.dest))
            live = (live - set(i.dest)) | i.uses()
            clique(live)
    colors = {}
    for name in sorted(graph, key=lambda x: (-len(graph[x]), x)):
        occupied = {colors[n] for n in graph[name] if n in colors}
        color = 0
        while color in occupied:
            color += 1
        colors[name] = color
    return {"live_in": {k: sorted(v) for k, v in inside.items()},
            "live_out": {k: sorted(v) for k, v in outside.items()},
            "graph": {k: sorted(v) for k, v in sorted(graph.items())},
            "colors": colors, "color_count": max(colors.values(), default=-1) + 1}

