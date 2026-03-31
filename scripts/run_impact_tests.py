#!/usr/bin/env python3
"""Run impacted pytest tests based on changed file paths.

Policy:
- For fast iteration, run only tests impacted by the code you changed.
- For milestones/releases, run the full suite.
- For docs-only changes, run nothing.

This script determines impacted tests from `git diff --name-only` and runs the
union of mapped test globs.

Examples:
  python scripts/run_impact_tests.py              # compare working tree vs HEAD
  python scripts/run_impact_tests.py --since HEAD~1
  python scripts/run_impact_tests.py --dry-run
  python scripts/run_impact_tests.py --all        # full suite

Exit codes:
- 0: tests (or no tests) succeeded
- non-zero: pytest failed or git error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Set


REPO_ROOT = Path(__file__).resolve().parents[1]


def _glob_exists(pattern: str) -> bool:
    # pytest errors out if a command-line arg doesn't match any path.
    # For globs, check whether they match at least one file.
    p = REPO_ROOT / pattern
    has_glob = any(ch in pattern for ch in ("*", "?", "["))
    if not has_glob:
        return p.exists()

    # pytest doesn't expand globs; we must resolve them ourselves.
    # Treat patterns with directory parts as workspace-relative.
    matches = list(REPO_ROOT.glob(pattern))
    return bool(matches)


def _run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _git_changed_paths(since: str) -> List[str]:
    # Use -- to avoid ambiguity when since looks like a path.
    res = _run(["git", "diff", "--name-only", since, "--"], cwd=REPO_ROOT)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or "git diff failed")
    paths = [p.strip() for p in res.stdout.splitlines() if p.strip()]

    # Include untracked files (e.g. newly added tests/scripts).
    st = _run(["git", "status", "--porcelain"], cwd=REPO_ROOT)
    if st.returncode == 0:
        for line in st.stdout.splitlines():
            # Format: '?? path'
            if line.startswith("?? "):
                p = line[3:].strip()
                if p:
                    paths.append(p)

    return paths


def _is_docs_only(paths: Iterable[str]) -> bool:
    for p in paths:
        if p.startswith("docs/") or p == "README.md" or p.endswith(".md"):
            continue
        return False
    return True


def _select_tests(paths: Iterable[str]) -> List[str]:
    """Map changed file paths to pytest targets (files or globs).

    Keep this coarse-grained and stable. Over time we can refine.
    """

    tests: Set[str] = set()

    for p in paths:
        # Explicit tests changes: run the changed tests.
        if p.startswith("tests/") and p.endswith(".py"):
            tests.add(p)
            continue

        # Docs-only changes don't add any tests.
        if p.startswith("docs/") or p == "README.md" or p.endswith(".md"):
            continue

        # Core compiler entrypoints / driver / orchestration
        if p in {"pycc.py", "pycc/compiler.py"} or p.startswith("pycc/compiler"):
            tests.update(
                {
                    "tests/test_driver_*.py",
                    "tests/test_compile_with_*.py",
                    "tests/test_multi_tu*.py",
                }
            )

        # Preprocessor
        if p.startswith("pycc/preprocessor"):
            tests.add("tests/test_preprocessor_*.py")
            tests.add("tests/test_compile_with_preprocessor.py")

        # Frontend
        if p.startswith("pycc/lexer"):
            tests.add("tests/test_lexer.py")
        if p.startswith("pycc/parser") or p.startswith("pycc/ast_nodes"):
            # Many parser/AST features are covered by feature tests.
            tests.add("tests/test_declarator_*.py")
            tests.add("tests/test_declarators.py")
            tests.add("tests/test_enum.py")
            tests.add("tests/test_initializers.py")

        # Semantics/types
        if p.startswith("pycc/semantics"):
            tests.update(
                {
                    "tests/test_const*.py",
                    "tests/test_member_*.py",
                    "tests/test_int_*.py",
                    "tests/test_integer_promotions*.py",
                    "tests/test_int_conversions*.py",
                    "tests/test_cast.py",
                }
            )

        # IR / optimizer / codegen
        if p.startswith("pycc/ir") or p.startswith("pycc/optimizer") or p.startswith("pycc/codegen"):
            tests.update(
                {
                    "tests/test_codegen*.py",
                    "tests/test_int_*.py",
                    "tests/test_integer_promotions*.py",
                    "tests/test_int_conversions*.py",
                    "tests/test_pointer_*.py",
                    "tests/test_glibc_smoke_*.py",
                }
            )

    # If we couldn't map anything but there were non-doc changes, fall back.
    if not tests and any(not (p.startswith("docs/") or p.endswith(".md") or p == "README.md") for p in paths):
        tests.add("tests")

    return sorted(tests)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_impact_tests", description=__doc__)
    ap.add_argument(
        "--since",
        default="HEAD",
        help="Revision to diff against (default: HEAD). Example: HEAD~1, origin/master",
    )
    ap.add_argument("--all", action="store_true", help="Run full test suite (pytest -q)")
    ap.add_argument("--dry-run", action="store_true", help="Print selected tests without running")
    ap.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Extra args passed to pytest, after '--'. Example: --pytest-args -q -k foo",
    )

    args = ap.parse_args(argv)

    if args.all:
        cmd = [sys.executable, "-m", "pytest", "-q", *args.pytest_args]
        if args.dry_run:
            print(" ".join(cmd))
            return 0
        return subprocess.call(cmd, cwd=str(REPO_ROOT))

    paths = _git_changed_paths(args.since)
    if not paths:
        # Nothing changed.
        return 0

    if _is_docs_only(paths):
        # Docs-only changes: skip tests.
        return 0

    tests = _select_tests(paths)
    # Expand globs into concrete files; drop any patterns that match nothing.
    expanded: List[str] = []
    for t in tests:
        if any(ch in t for ch in ("*", "?", "[")):
            expanded.extend(sorted(str(p.relative_to(REPO_ROOT)) for p in REPO_ROOT.glob(t)))
        elif (REPO_ROOT / t).exists():
            expanded.append(t)
    tests = sorted(set(expanded))
    cmd = [sys.executable, "-m", "pytest", "-q", *tests, *args.pytest_args]

    if args.dry_run:
        sys.stdout.write("# changed paths\n")
        sys.stdout.write("\n".join(paths) + "\n")
        sys.stdout.write("# selected tests\n")
        sys.stdout.write("\n".join(tests) + "\n")
        sys.stdout.write("# command\n")
        sys.stdout.write(" ".join(cmd) + "\n")
        return 0

    return subprocess.call(cmd, cwd=str(REPO_ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
