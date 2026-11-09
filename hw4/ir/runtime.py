"""Small IR interpreter for checking that optimizations preserve execution."""


def int32(n):
    return (n + 2**31) % 2**32 - 2**31


def calculate(op, args):
    if op == "neg":
        return int32(-args[0])
    if op == "not":
        return not args[0]
    x, y = args
    if op == "+":
        return int32(x + y)
    if op == "-":
        return int32(x - y)
    if op == "*":
        return int32(x * y)
    if op == "/":
        q = abs(x) // abs(y)
        return int32(-q if (x < 0) != (y < 0) else q)
    if op == "==":
        return x == y
    if op == "!=":
        return x != y
    if op == "<":
        return x < y
    if op == "<=":
        return x <= y
    if op == ">":
        return x > y
    if op == ">=":
        return x >= y
    if op == "and":
        return x and y
    if op == "or":
        return x or y
    if op == "->":
        return not x or y
    raise ValueError(f"unknown operation: {op}")


def execute(functions, name, args, budget=None):
    if budget is None:
        budget = [100000]
    f = next(f for f in functions if f.name == name)
    if len(args) != len(f.params):
        raise ValueError("wrong argument count")
    env = dict(zip(f.params, args))
    blocks = {b.label: b for b in f.blocks}
    label = f.blocks[0].label
    while True:
        for i in blocks[label].code:
            budget[0] -= 1
            if budget[0] < 0:
                raise RuntimeError("instruction limit exceeded")
            values = [env[x] if isinstance(x, str) else x for x in i.args]
            if i.op == "jump":
                label = i.target[0]
                break
            if i.op == "branch":
                label = i.target[0 if values[0] else 1]
                break
            if i.op == "return":
                return values
            if i.op == "call":
                results = execute(functions, i.name, values, budget)
            elif i.op == "copy":
                results = [values[0][:] if isinstance(values[0], list) else values[0]]
            elif i.op == "length":
                results = [len(values[0])]
            elif i.op in {"load", "update"}:
                arr, index = values[:2]
                if not 0 <= index < len(arr):
                    raise IndexError("array index out of bounds")
                if i.op == "load":
                    results = [arr[index]]
                else:
                    arr = arr[:]
                    arr[index] = values[2]
                    results = [arr]
            else:
                results = [calculate(i.op, values)]
            env.update(zip(i.dest, results))
