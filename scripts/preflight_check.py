"""PREFLIGHT -- run this before restarting the backend, every time.

WHY THIS EXISTS (2026-08-31): a session added Marcus's store tools to main.py
using `LEGAL_ID`, which was never imported. It ran an `ast.parse` syntax check,
got "syntax ok", and shipped. A syntax check only proves the file PARSES -- it
cannot see an undefined name, because that is a runtime error. The backend then
500'd on EVERY chat (the bad line sits in the shared path all nine seats run
through) and Barry lost Victor.

It hid for 11 hours because the line lives inside `if not is_offline_mode():`
and Offline Mode was ON when it was tested. So a green test proved nothing.

This checks the things a syntax check misses:
  1. UNRESOLVED NAMES  -- the LEGAL_ID class of bug, per module.
  2. MODULE ATTRIBUTES -- every `llm_router.X` / `memory.X` style reference
     actually exists on that module (catches a tool constant that was wired
     into main.py but never defined).
  3. REAL IMPORT       -- each backend module imports without executing the app.
  4. ROUTE COLLISIONS  -- two handlers on the same method+path (the later one
     silently wins, which is how a working endpoint disappears).

Read-only. Touches no database, starts no server, sends nothing.
Exit code 0 = safe to restart. Non-zero = do NOT restart.

    venv/Scripts/python.exe scripts/preflight_check.py
"""

from __future__ import annotations

import ast
import builtins
import os
import re
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")

problems: list[str] = []
notes: list[str] = []


def _py_files() -> list[str]:
    return sorted(f for f in os.listdir(BACKEND) if f.endswith(".py"))


def _bound_names(tree: ast.AST) -> set[str]:
    """Every name that exists somewhere in the module's scopes.

    Deliberately generous -- this is a smoke test, not a type checker. A false
    NEGATIVE (missing a real bug) costs an outage; a false POSITIVE costs Barry
    a confusing red line. So when in doubt, treat a name as bound.
    """
    names = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            args = node.args
            for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                names.add(a.arg)
            if args.vararg:
                names.add(args.vararg.arg)
            if args.kwarg:
                names.add(args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            names.update(node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def check_unresolved_names() -> None:
    print("[1/5] unresolved names")
    for fname in _py_files():
        path = os.path.join(BACKEND, fname)
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError as exc:
            problems.append(f"{fname}: SYNTAX ERROR line {exc.lineno}: {exc.msg}")
            continue
        bound = _bound_names(tree)
        bad = sorted(
            {
                n.id
                for n in ast.walk(tree)
                if isinstance(n, ast.Name)
                and isinstance(n.ctx, ast.Load)
                and n.id not in bound
                and n.id != "__file__"
            }
        )
        if bad:
            problems.append(f"{fname}: undefined name(s): {', '.join(bad)}")
    print("      ok" if not problems else f"      {len(problems)} problem(s)")


def check_module_attributes() -> None:
    """`llm_router.SOME_TOOL` referenced in main.py but never defined there.

    This is the sibling of the LEGAL_ID bug: the name resolves (the module IS
    imported) but the attribute does not exist, so it dies at runtime instead.
    """
    print("[2/5] cross-module attribute references")
    modules = {f[:-3] for f in _py_files()}
    defined: dict[str, set[str]] = {}
    for mod in modules:
        try:
            tree = ast.parse(open(os.path.join(BACKEND, mod + ".py"), encoding="utf-8").read())
        except SyntaxError:
            continue
        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.If, ast.Try)):
                # config flags and try/except ALTER-style guarded definitions
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Assign):
                        for t in sub.targets:
                            if isinstance(t, ast.Name):
                                names.add(t.id)
                    elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(sub.name)
        defined[mod] = names

    misses = 0
    for fname in _py_files():
        try:
            tree = ast.parse(open(os.path.join(BACKEND, fname), encoding="utf-8").read())
        except SyntaxError:
            continue
        imported = {
            (a.asname or a.name).split(".")[0]
            for n in ast.walk(tree)
            if isinstance(n, ast.Import)
            for a in n.names
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in imported
                and node.value.id in defined
                and node.attr not in defined[node.value.id]
                and not node.attr.startswith("__")
            ):
                problems.append(
                    f"{fname}:{node.lineno}: {node.value.id}.{node.attr} "
                    f"is not defined in {node.value.id}.py"
                )
                misses += 1
    print("      ok" if not misses else f"      {misses} missing attribute(s)")


def check_imports() -> None:
    """Actually import each module. Catches import-time errors nothing static can."""
    print("[3/5] real imports")
    sys.path.insert(0, BACKEND)
    os.environ.setdefault("PREFLIGHT", "1")
    failed = 0
    for fname in _py_files():
        mod = fname[:-3]
        if mod == "main":
            # main.py builds the FastAPI app at import time; skipped on purpose
            # so preflight never touches ports, the DB, or a lifespan task.
            notes.append("main.py import skipped (builds the app) -- covered by checks 1, 2 and 4")
            continue
        try:
            __import__(mod)
        except Exception as exc:  # noqa: BLE001 -- reporting, not handling
            problems.append(f"{fname}: import failed: {type(exc).__name__}: {exc}")
            failed += 1
    print("      ok" if not failed else f"      {failed} import failure(s)")


def check_local_import_shadowing() -> None:
    """A function that does `import X` INSIDE its body makes `X` local to the
    WHOLE function -- so any other branch that reads `X` before that line
    raises UnboundLocalError at runtime, only on that branch, only when it is
    taken. 2026-09-02/03: `_dispatch_tool_call` had a local `import memory` in
    one tool branch; `inspect_brain` (Taliyah) and `change_my_picture` (Derek)
    died with "cannot access local variable 'memory'" and Bonsai 'failed' onto
    the 9b. A syntax check and the undefined-name check both pass this. Flag
    any function that locally imports a name the module also imports at top
    level AND reads that name somewhere the local import does not dominate."""
    print("[5/5] local imports shadowing module names")
    hits = 0
    for fname in _py_files():
        path = os.path.join(BACKEND, fname)
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        top_imports = {
            (a.asname or a.name).split(".")[0]
            for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names
        }
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            local_imports: dict[str, int] = {}
            for node in ast.walk(fn):
                if isinstance(node, (ast.Import, ast.ImportFrom)) and node is not fn:
                    for a in node.names:
                        nm = (a.asname or a.name).split(".")[0]
                        if nm in top_imports:
                            local_imports.setdefault(nm, node.lineno)
            if not local_imports:
                continue
            for node in ast.walk(fn):
                if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
                        and node.id in local_imports and node.lineno < local_imports[node.id]):
                    problems.append(
                        f"{fname}:{node.lineno}: `{node.id}` is read in {fn.name}() but a LOCAL "
                        f"`import {node.id}` at line {local_imports[node.id]} makes it a local "
                        f"variable for the whole function -> UnboundLocalError on this branch. "
                        f"Delete the local import (the module already imports it at top level).")
                    hits += 1
                    break
    print("      ok" if not hits else f"      {hits} shadowing bug(s)")


def check_route_collisions() -> None:
    print("[4/5] duplicate routes")
    src = open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
    seen: dict[tuple[str, str], int] = {}
    dupes = 0
    for m in re.finditer(r'@app\.(get|post|put|delete)\("([^"]+)"', src):
        key = (m.group(1), m.group(2))
        line = src.count("\n", 0, m.start()) + 1
        if key in seen:
            problems.append(
                f"main.py:{line}: duplicate route {key[0].upper()} {key[1]} "
                f"(first defined line {seen[key]}) -- the LATER one silently wins"
            )
            dupes += 1
        else:
            seen[key] = line
    print(f"      ok ({len(seen)} routes)" if not dupes else f"      {dupes} collision(s)")


def main() -> int:
    print("PREFLIGHT -- backend/\n")
    try:
        check_unresolved_names()
        check_module_attributes()
        check_imports()
        check_route_collisions()
        check_local_import_shadowing()
    except Exception:  # noqa: BLE001
        print("\npreflight itself crashed:")
        traceback.print_exc()
        return 2

    print()
    for n in notes:
        print(f"note: {n}")
    if problems:
        print(f"\n*** {len(problems)} PROBLEM(S) -- DO NOT RESTART THE BACKEND ***\n")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nALL CLEAR -- safe to restart the backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
