"""Optional block-local constant propagation, algebraic simplification and DCE."""

from copy import deepcopy
from .analysis import liveness
from .model import Instr
from .runtime import calculate

ARITHMETIC = {"+", "-", "*", "/", "neg", "not", "==", "!=", "<", "<=", ">", ">=", "and", "or", "->"}
# Operations that cannot raise or call user code. Division and array operations stay.
REMOVABLE = (ARITHMETIC - {"/"}) | {"copy"}


def optimize(functions, constants=True, algebra=True, dce=True):
    result = deepcopy(functions)
    for f in result:
        for b in f.blocks:
            known = {}
            for n, original in enumerate(b.code):
                i = deepcopy(original)
                if constants:
                    i.args = [known.get(x, x) if isinstance(x, str) else x for x in i.args]
                    if i.op in ARITHMETIC and all(not isinstance(x, str) for x in i.args):
                        try:
                            value = calculate(i.op, i.args)
                        except ZeroDivisionError:
                            pass
                        else:
                            i = Instr("copy", i.dest, [value])
                if algebra and len(i.args) == 2:
                    x, y = i.args
                    replacement = None
                    if (i.op in {"+", "-"} and y == 0) or (i.op in {"*", "/"} and y == 1):
                        replacement = x
                    elif (i.op == "+" and x == 0) or (i.op == "*" and x == 1):
                        replacement = y
                    elif i.op == "*" and (x == 0 or y == 0):
                        replacement = 0
                    if replacement is not None:
                        i = Instr("copy", i.dest, [replacement])
                for dest in i.dest:
                    known.pop(dest, None)
                if i.op == "copy" and not isinstance(i.args[0], str):
                    known[i.dest[0]] = i.args[0]
                b.code[n] = i
        if dce:
            changed = True
            while changed:
                changed = False
                _, outside = liveness(f)
                for b in f.blocks:
                    live = set(outside[b.label])
                    kept = []
                    for i in reversed(b.code):
                        if i.op in REMOVABLE and i.dest and not (set(i.dest) & live):
                            changed = True
                            continue
                        live = (live - set(i.dest)) | i.uses()
                        kept.append(i)
                    b.code = list(reversed(kept))
    return result
