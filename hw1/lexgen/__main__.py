"""CLI:  python -m lexgen {build,test} ...   (run `python -m lexgen -h`)"""

import argparse
import sys
from pathlib import Path

from .build import build
from .cases import load_cases, run_case
from .spec import SpecError, load_spec

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPEC = ROOT / "tokens.spec"
DEFAULT_CASES = ROOT / "tests" / "cases.tsv"


def cmd_build(args: argparse.Namespace) -> int:
    b = build(load_spec(args.spec))
    print(f"rules:            {len(b.rules)}")
    print(f"NFA states:       {b.nfa.size}")
    print(f"DFA states:       {b.dfa.size} (incl. trap)")
    print(f"min DFA states:   {b.min_dfa.size} (incl. trap)")
    if args.json:
        b.table.save(args.json)
        print(f"table written to  {args.json}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases)
    b = build(load_spec(args.spec))
    # The same cases on the DFA before minimization: both must agree with the expectations.
    tables = {"min": b.table, "raw": b.unminimized_table}
    failed = 0
    for case in cases:
        results = {name: run_case(t, case) for name, t in tables.items()}
        ok = all(r == case.expected for r in results.values())
        failed += not ok
        shown = " | ".join(f"{n}: {r}" for n, r in results.items()) if not ok else case.expected
        print(f"{'PASS' if ok else 'FAIL'}  {case.kind:5} {case.input!r:32} -> {shown}"
              + ("" if ok else f"   (expected: {case.expected}, line {case.lineno})"))
    print(f"\n{len(cases) - failed}/{len(cases)} passed on: {', '.join(tables)}")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lexgen", description="Regex -> NFA -> DFA -> minimal DFA lexer generator")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("build", help="build the minimal DFA, print sizes, export it")
    p.add_argument("--spec", default=DEFAULT_SPEC)
    p.add_argument("--json", help="write the transition table as JSON")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("test", help="run test cases and print their statuses")
    p.add_argument("cases", nargs="?", default=DEFAULT_CASES)
    p.add_argument("--spec", default=DEFAULT_SPEC)
    p.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (SpecError, OSError, ValueError) as e:
        print(f"lexgen: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
