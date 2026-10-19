"""CLI:  python -m funny {parse,test} ...   (run `python -m funny -h`)"""

import argparse
import json
import sys
from pathlib import Path

from .ast import dump, to_json
from .lexer import DEFAULT_TABLE, Table
from .parser import parse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TESTS = ROOT / "tests"


def cmd_parse(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    program, errors = parse(text, Table.load(args.table))
    for e in errors:
        print(f"{args.file}:{e}", file=sys.stderr)
    if program is None:
        return 1
    print(json.dumps(to_json(program), indent=2) if args.json else dump(program), end="\n" if args.json else "")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """Every tests/**/NAME.funny has NAME.ast (the expected AST dump) or NAME.err (the expected errors)."""
    table = Table.load(args.table)
    sources = sorted(Path(args.dir).rglob("*.funny"))
    failed = 0
    for src in sources:
        name = src.relative_to(args.dir).as_posix()
        program, errors = parse(src.read_text(encoding="utf-8"), table)
        actual = dump(program) if program else "".join(f"{e}\n" for e in errors)
        expected_file = next((f for f in (src.with_suffix(".ast"), src.with_suffix(".err")) if f.exists()), None)
        if expected_file is None:
            ok, why = False, "no .ast or .err file"
        elif (expected_file.suffix == ".ast") != (program is not None):
            ok, why = False, f"expected {'an AST' if expected_file.suffix == '.ast' else 'errors'}, got:\n{actual}"
        else:
            expected = expected_file.read_text(encoding="utf-8")
            ok, why = actual == expected, first_difference(expected, actual)
        failed += not ok
        kind = "ast" if program else "err"
        print(f"{'PASS' if ok else 'FAIL'}  {kind}  {name}" + ("" if ok else f"\n      {why}"))
    print(f"\n{len(sources) - failed}/{len(sources)} passed")
    return 1 if failed else 0


def first_difference(expected: str, actual: str) -> str:
    exp, act = expected.splitlines(), actual.splitlines()
    for n, (e, a) in enumerate(zip(exp, act), 1):
        if e != a:
            return f"line {n}: expected {e!r}, got {a!r}"
    return f"expected {len(exp)} lines, got {len(act)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="funny", description="LL(1) parser of Funny: program -> AST")
    parser.add_argument("--table", default=DEFAULT_TABLE, help="lexer table exported by HW1 (default: ../hw1/out/dfa.json)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("parse", help="parse a file ('-' for stdin), print the AST or the errors")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="print the AST as JSON instead of the text dump")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("test", help="parse every tests/**/*.funny and compare with its .ast / .err file")
    p.add_argument("dir", nargs="?", default=DEFAULT_TESTS)
    p.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as e:
        print(f"funny: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
