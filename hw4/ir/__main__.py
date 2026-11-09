"""CLI: python -m ir {build,test}."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import unittest

from funny.lexer import Table
from funny.parser import parse
from sema.checker import check
from .analysis import allocate
from .lower import lower
from .model import dump
from .optimize import optimize

ROOT = Path(__file__).resolve().parent.parent


def compile_source(text):
    program, errors = parse(text, Table.load())
    if program is not None and not errors:
        errors = check(program)
    return (lower(program) if not errors else None), errors


def metrics(f):
    names = {x for b in f.blocks for i in b.code for x in i.dest + list(i.uses())}
    return {"instructions": sum(len(b.code) for b in f.blocks),
            "temporaries": sum(x.startswith("%") for x in names)}


def cmd_build(args):
    source = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    compiled, errors = compile_source(source)
    if errors:
        for e in errors:
            print(f"{args.file}:{e}", file=sys.stderr)
        return 1
    before, formulas = compiled
    after = optimize(before, constants=not (args.no_opt or args.no_constants),
                     algebra=not (args.no_opt or args.no_algebra), dce=not (args.no_opt or args.no_dce))
    allocations = {f.name: allocate(f) for f in after}
    counts = {f.name: {"before": metrics(f), "after": metrics(g)} for f, g in zip(before, after)}
    if args.json:
        print(json.dumps({"before": [asdict(f) for f in before], "after": [asdict(f) for f in after],
                          "formulas": formulas, "allocation": allocations, "metrics": counts}, indent=2))
    else:
        print("Before:\n" + dump(before) + "After:\n" + dump(after), end="")
        print("Allocation:\n" + json.dumps(allocations, indent=2))
        print("Metrics:\n" + json.dumps(counts, indent=2))
    return 0


def cmd_test(args):
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ir", description="Funny: typed AST -> IR, CFG, optimizations, coloring")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build", help="compile a file ('-' for stdin)")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-opt", action="store_true", help="disable all optimizations")
    p.add_argument("--no-constants", action="store_true")
    p.add_argument("--no-algebra", action="store_true")
    p.add_argument("--no-dce", action="store_true")
    p.set_defaults(func=cmd_build)
    p = sub.add_parser("test", help="run HW4 tests")
    p.set_defaults(func=cmd_test)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as e:
        print(f"ir: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
