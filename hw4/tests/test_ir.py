"""Execution equivalence, CFG/liveness invariants and regression cases."""

import itertools
from pathlib import Path
import unittest

from ir.__main__ import compile_source, metrics
from ir.analysis import allocate, liveness
from ir.model import Block, Function, Instr, dump
from ir.optimize import optimize
from ir.runtime import execute

ROOT = Path(__file__).resolve().parent


def compile_ok(source):
    result, errors = compile_source(source)
    if errors:
        raise AssertionError("\n".join(map(str, errors)))
    return result[0]


class IRTests(unittest.TestCase):
    def compare(self, source, name, cases, expected):
        before = compile_ok(source)
        for flags in itertools.product((False, True), repeat=3):
            after = optimize(before, *flags)
            for args, want in zip(cases, expected):
                with self.subTest(flags=flags, args=args):
                    self.assertEqual(execute(before, name, args), want)
                    self.assertEqual(execute(after, name, args), want)
            self.check_graph(after)
        return before, optimize(before)

    def check_graph(self, functions):
        for f in functions:
            allocation = allocate(f)
            graph, colors = allocation["graph"], allocation["colors"]
            inside, outside = liveness(f)
            labels = {b.label for b in f.blocks}
            for b in f.blocks:
                self.assertIn(b.code[-1].op, {"branch", "jump", "return"})
                self.assertTrue(set(b.successors()) <= labels)
                self.assertEqual(outside[b.label], set().union(*(inside[s] for s in b.successors())))
            for x, neighbors in graph.items():
                for y in neighbors:
                    self.assertIn(x, graph[y])
                    self.assertNotEqual(colors[x], colors[y])

    def test_constants_and_dce(self):
        before, after = self.compare((ROOT / "basic.funny").read_text(), "calc",
                                     [[-3], [0], [7]], [[17], [20], [27]])
        self.assertLess(metrics(after[0])["instructions"], metrics(before[0])["instructions"])
        self.assertEqual(dump(before), (ROOT / "basic.before.ir").read_text())
        self.assertEqual(dump(after), (ROOT / "basic.after.ir").read_text())

    def test_loop_nested_branch(self):
        self.compare((ROOT / "control.funny").read_text(), "sum",
                     [[-1], [0], [1], [4], [7]], [[0], [0], [0], [0], [9]])

    def test_recursion(self):
        self.compare((ROOT / "control.funny").read_text(), "fact",
                     [[0], [1], [5], [8]], [[1], [1], [120], [40320]])

    def test_arrays_multiple_return(self):
        self.compare((ROOT / "arrays.funny").read_text(), "arrays",
                     [[[3, 4], 9], [[-2], 5]], [[[9, 4], 19], [[5], 7]])

    def test_redefinition_and_block_boundary(self):
        self.compare('''f(x:int) returns r:int {
            a = 3; a = x; r = a + 1;
            if (x > 0) r = 10; else r = r + a;
            r = r + 2;
        }''', "f", [[-2], [0], [1]], [[-1], [3], [12]])

    def test_wraparound_and_division(self):
        self.compare('''f(x:int) returns a:int, b:int, c:int {
            a = 2147483647 + 1; b = x / 3; c = (-2147483647 - 1) / -1;
        }''', "f", [[-7], [7]],
                     [[-2147483648, -2, -2147483648], [-2147483648, 2, -2147483648]])

    def test_exceptions_are_preserved(self):
        cases = [
            ("f(x:int) returns r:int { dead = 1 / x; r = 0; }", [0], ZeroDivisionError),
            ("f(a:int[]) returns r:int { dead = a[0]; r = 0; }", [[]], IndexError),
            ("f(a:int[]) returns r:int { b = a; b[-1] = 7; r = 0; }", [[1]], IndexError),
            ("g(x:int) returns r:int { r = 1 / x; } f(x:int) returns r:int { dead = g(x); r = 0; }", [0], ZeroDivisionError),
        ]
        for source, args, error in cases:
            before = compile_ok(source)
            for functions in [before, optimize(before)]:
                with self.assertRaises(error):
                    execute(functions, "f", args)

    def test_annotations_and_formulas(self):
        source = '''positive(x:int) => x > 0;
        f(x:int) requires positive(x) returns r:int ensures r > 0 {
            r = x; assert positive(r); assume r > 0;
            while (r < 2) invariant r > 0 { r = r + 1; }
        }'''
        compiled, errors = compile_source(source)
        self.assertFalse(errors)
        functions, formulas = compiled
        self.assertEqual(len(formulas), 1)
        self.assertEqual([x["kind"] for x in functions[0].annotations],
                         ["requires", "assert", "assume", "invariant", "ensures"])
        self.assertEqual(execute(optimize(functions), "f", [1]), [2])

    def test_bad_input(self):
        for source in ["f(x:int) returns r:int { r = missing; }", "f("]:
            compiled, errors = compile_source(source)
            self.assertIsNone(compiled)
            self.assertTrue(errors)

    def test_live_across_loop(self):
        f = compile_ok((ROOT / "control.funny").read_text())[0]
        inside, _ = liveness(f)
        self.assertTrue({"i", "n", "r"} <= inside["B1"])

    def test_interference_of_simultaneous_values(self):
        f = Function("f", ["x", "y"], ["r"], {"x": "int", "y": "int", "r": "int"},
                     [Block("B0", [Instr("+", ["r"], ["x", "y"]), Instr("return", args=["r"])])])
        self.assertIn("y", allocate(f)["graph"]["x"])
        self.check_graph([f])

    def test_all_hw3_positive_examples(self):
        directory = ROOT.parents[1] / "hw3" / "tests"
        for expected in sorted(directory.rglob("*.typed")):
            with self.subTest(file=expected.name):
                functions = compile_ok(expected.with_suffix(".funny").read_text())
                self.check_graph(optimize(functions))


if __name__ == "__main__":
    unittest.main()
