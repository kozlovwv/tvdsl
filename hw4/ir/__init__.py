"""Three-address IR, local optimizations and register allocation for Funny."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hw3"))
import sema  # also makes the HW2 parser available
