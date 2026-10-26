"""Semantic checks of Funny: names, types, inference of local types. Uses the parser and AST of HW2."""

import sys
from pathlib import Path

# The `funny` package (lexer, parser, AST) lives in ../hw2.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hw2"))
