"""Automated code checks for Phase 14 (MNT-2, MNT-3, SEC-4, USE-5), shared by tests/test_code_quality.py and
scripts/measure_phase14.py.

    python scripts/code_checks.py          # print every finding

Each check reads the source with Python's own parser (ast), so it sees the code exactly as Python does.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "plasma_twin"
APP = ROOT / "app"
PHYSICS = ("stage1", "stage2", "oes", "probe", "compare", "reference", "config")
STATUS_CALLS = ("success", "info", "warning", "error")


def python_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*.py") if "__pycache__" not in p.parts)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


# ------------------------------------------------------------------------------------ MNT-3
@dataclass(frozen=True)
class FunctionGap:
    where: str  # file:line
    name: str
    missing: tuple[str, ...]  # "docstring", "return annotation", "annotation for x"


def _public_functions(tree: ast.Module):
    """Module-level functions and the methods of module-level classes whose names do not start with "_"."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            yield node.name, node
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("_"):
                    yield f"{node.name}.{item.name}", item


def function_gaps(folder: Path = PACKAGE) -> tuple[int, list[FunctionGap]]:
    """MNT-3: (public functions counted, the ones missing a docstring or a type hint)."""
    total, gaps = 0, []
    for path in python_files(folder):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, node in _public_functions(tree):
            total += 1
            missing = []
            if ast.get_docstring(node) is None:
                missing.append("docstring")
            if node.returns is None:
                missing.append("return annotation")
            arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            arguments += [a for a in (node.args.vararg, node.args.kwarg) if a is not None]
            for argument in arguments:
                if argument.arg not in ("self", "cls") and argument.annotation is None:
                    missing.append(f"annotation for {argument.arg}")
            if missing:
                gaps.append(FunctionGap(f"{_relative(path)}:{node.lineno}", name, tuple(missing)))
    return total, gaps


# ------------------------------------------------------------------------------------ MNT-2
ROUND = {0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 100.0, 1000.0, 0.5, 0.25, 0.1, 1e-3, 1e-6, 1e-9, 1e3, 1e6, 1e9, 60.0}


def significant_figures(value: float) -> int:
    text = f"{abs(value):.12g}".split("e")[0].replace(".", "").lstrip("0").rstrip("0")
    return len(text)


def numeric_literals(folders: tuple[str, ...] = PHYSICS) -> list[tuple[str, float]]:
    """MNT-2: numbers with 3 or more significant figures inside functions of the physics modules."""
    found = []
    for folder in folders:
        for path in python_files(PACKAGE / folder):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(function):
                    if (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
                            and not isinstance(node.value, bool) and float(node.value) not in ROUND
                            and significant_figures(float(node.value)) >= 3):
                        found.append((f"{_relative(path)}:{node.lineno}", float(node.value)))
    return sorted(set(found))


# ------------------------------------------------------------------------------------ SEC-4
def unsafe_sql(folder: Path = PACKAGE) -> list[str]:
    """SEC-4: execute()/executemany()/executescript() calls whose SQL is built from text (f-string, % or +)."""
    found = []
    for path in python_files(folder):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("execute", "executemany", "executescript") and node.args):
                sql = node.args[0]
                if isinstance(sql, ast.JoinedStr) or (isinstance(sql, ast.BinOp) and isinstance(sql.op, (ast.Mod, ast.Add))) \
                        or (isinstance(sql, ast.Call) and isinstance(sql.func, ast.Attribute) and sql.func.attr == "format"):
                    found.append(f"{_relative(path)}:{node.lineno}")
    return found


def sql_calls(folder: Path = PACKAGE) -> int:
    count = 0
    for path in python_files(folder):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executemany", "executescript"):
                count += 1
    return count


# ------------------------------------------------------------------------------------ USE-5
def bare_status_calls(folder: Path = APP) -> list[str]:
    """USE-5: st.success/info/warning/error used directly (colour only) instead of through status()."""
    found = []
    for path in python_files(folder):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed: set[int] = set()
        for function in ast.walk(tree):
            if isinstance(function, ast.FunctionDef) and function.name == "status":
                allowed |= {n.lineno for n in ast.walk(function) if hasattr(n, "lineno")}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr in STATUS_CALLS and isinstance(node.value, ast.Name)
                    and node.value.id == "st" and node.lineno not in allowed):
                found.append(f"{_relative(path)}:{node.lineno} st.{node.attr}")
    return found


# ------------------------------------------------------------------------------------ MNT-1 (test files)
def modules_without_tests() -> list[str]:
    """Domain modules whose name appears in no test file (MNT-1 asks for a test file per module)."""
    import re
    tests = " ".join(p.read_text(encoding="utf-8") for p in python_files(ROOT / "tests"))
    missing = []
    for path in python_files(PACKAGE):
        if path.name != "__init__.py" and not re.search(r"\b" + re.escape(path.stem) + r"\b", tests):
            missing.append(_relative(path))
    return missing


def main() -> None:
    total, gaps = function_gaps()
    print(f"MNT-3: {total} public functions, {len(gaps)} with a gap")
    for gap in gaps:
        print(f"  {gap.where} {gap.name}: {', '.join(gap.missing)}")
    literals = numeric_literals()
    print(f"MNT-2: {len(literals)} numbers with 3+ significant figures in physics functions")
    for where, value in literals:
        print(f"  {where} {value:g}")
    print(f"SEC-4: {sql_calls()} SQL calls, built from text: {unsafe_sql() or 'none'}")
    print(f"USE-5: direct status calls: {bare_status_calls() or 'none'}")
    print(f"MNT-1: modules no test refers to: {modules_without_tests() or 'none'}")


if __name__ == "__main__":
    sys.exit(main())
