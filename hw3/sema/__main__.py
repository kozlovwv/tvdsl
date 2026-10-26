"""CLI:  python -m sema {check,test} ...   (run `python -m sema -h`)"""

import argparse
import json
import sys
from pathlib import Path

from funny.lexer import Table
from funny.parser import parse

from .annotated import dump, to_json
from .checker import check

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TESTS = ROOT / "tests"


def cmd_check(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    program, errors = parse(text, Table.load())
    if program is not None:
        errors = check(program)
        if not errors:
            print(json.dumps(to_json(program), indent=2) if args.json else dump(program), end="\n" if args.json else "")
    for e in errors:
        print(f"{args.file}:{e}", file=sys.stderr)
    return 1 if errors else 0


def cmd_test(args: argparse.Namespace) -> int:
    """Every tests/**/NAME.funny has NAME.typed (the expected annotated AST) or NAME.err (the expected errors:
    syntax errors, or semantic errors of a program that parses)."""
    table = Table.load()
    sources = sorted(Path(args.dir).rglob("*.funny"))
    failed = 0
    for src in sources:
        name = src.relative_to(args.dir).as_posix()
        program, errors = parse(src.read_text(encoding="utf-8"), table)
        if program is not None:
            errors = check(program)
        actual = "".join(f"{e}\n" for e in errors) if errors else dump(program)
        expected_file = next((f for f in (src.with_suffix(".typed"), src.with_suffix(".err")) if f.exists()), None)
        if expected_file is None:
            ok, why = False, "no .typed or .err file"
        elif (expected_file.suffix == ".typed") != (not errors):
            ok, why = False, f"expected {'a typed AST' if expected_file.suffix == '.typed' else 'errors'}, got:\n{actual}"
        else:
            expected = expected_file.read_text(encoding="utf-8")
            ok, why = actual == expected, first_difference(expected, actual)
        failed += not ok
        kind = "err" if errors else "typed"
        print(f"{'PASS' if ok else 'FAIL'}  {kind:5}  {name}" + ("" if ok else f"\n      {why}"))
    print(f"\n{len(sources) - failed}/{len(sources)} passed")
    return 1 if failed else 0


def first_difference(expected: str, actual: str) -> str:
    exp, act = expected.splitlines(), actual.splitlines()
    for n, (e, a) in enumerate(zip(exp, act), 1):
        if e != a:
            return f"line {n}: expected {e!r}, got {a!r}"
    return f"expected {len(exp)} lines, got {len(act)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sema", description="Name and type checks of Funny: program -> typed AST")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="check a file ('-' for stdin), print the typed AST and the errors")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="print the typed AST as JSON instead of the text dump")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("test", help="check every tests/**/*.funny and compare with its .typed / .err file")
    p.add_argument("dir", nargs="?", default=DEFAULT_TESTS)
    p.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as e:
        print(f"sema: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
