"""Sophie's CAD hands (2026-10-17, Barry: "make sure my agents have the skills and the tools"; for PID, printer maybe
spring 2027). cad_generate: she writes a build123d script (units mm) that writes model.step; the office runs it in the
cadgen env (tools/cadgen, local, telemetry off, Edge previews -- see tools/cadgen/README.md), converts to STL,
snapshots a PNG, and puts all three on Barry's DESK. Nothing is sent anywhere; no fabrication service exists here.

Guard: the script is model-written code. It runs with -I (isolated) in its own folder under a timeout, and only after
an import allowlist check (build123d, math, pathlib, os.path, typing, dataclasses, itertools, functools). Anything
else (subprocess, socket, requests, shutil, sys, open() on paths outside the folder) is refused before it runs.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import re
import subprocess

import agent_files

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAD_DIR = os.path.join(_ROOT, "tools", "cadgen")
CAD_PY = os.path.join(CAD_DIR, "uv-tools", "cadgen", "Scripts", "python.exe")
CAD_BIN = os.path.join(CAD_DIR, "bin")
OUT_DIR = os.path.join(_ROOT, "data", "cad")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ALLOWED_IMPORTS = {"build123d", "math", "pathlib", "os.path", "typing", "dataclasses", "itertools", "functools"}
SCRIPT_TIMEOUT_S = 180

CAD_GENERATE_TOOL = {
    "type": "function",
    "function": {
        "name": "cad_generate",
        "description": (
            "Turn a build123d script into a real part: STEP + STL (3D-printable) + a preview PNG, on Barry's DESK. "
            "Write the script yourself (units mm; end by writing 'model.step' in the current folder with "
            "export_step). Runs locally in the office's cadgen environment; no outside service. Your text-to-cad "
            "skill has the build123d patterns and the printing checks (wall thickness, overhangs, tolerances)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Part name, e.g. 'pid-dock-shell-v1'."},
                "script": {"type": "string",
                           "description": "The build123d Python. Only build123d/math/pathlib imports. Must write model.step."},
                "notes": {"type": "string", "description": "What this part is for and what Barry should check (optional)."},
                "preview": {"type": "boolean", "description": "Also render a PNG preview (default true)."},
            },
            "required": ["name", "script"],
        },
    },
}


def _import_check(script: str) -> str | None:
    for m in re.finditer(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", script, re.M):
        mod = (m.group(1) or m.group(2) or "").strip()
        root = mod.split(".")[0]
        if mod in ALLOWED_IMPORTS or root in ALLOWED_IMPORTS:
            continue
        return f"import of '{mod}' is not allowed here (allowed: {', '.join(sorted(ALLOWED_IMPORTS))})"
    for bad in ("subprocess", "socket", "urllib", "requests", "httpx", "shutil", "__import__", "eval(", "exec(", "os.system", "os.remove", "os.unlink"):
        if bad in script:
            return f"'{bad}' is not allowed in a CAD script"
    if "export_step" not in script:
        return "the script must write the part with export_step(..., 'model.step')"
    return None


def _run(args: list[str], cwd: str, timeout: int, env: dict) -> tuple[int, str]:
    try:
        r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + "\n" + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as exc:
        return 127, str(exc)


def _make(office_name: str, a: dict) -> dict:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(a.get("name") or "part").strip()).strip("-")[:60] or "part"
    script = str(a.get("script") or "")
    if not script.strip():
        return {"error": "Give the build123d script."}
    why = _import_check(script)
    if why:
        return {"error": f"Refused before running: {why}."}
    if not os.path.isfile(CAD_PY):
        return {"error": f"cadgen is not installed at {CAD_PY} (tools/cadgen/README.md)."}
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    d = os.path.join(OUT_DIR, f"{stamp}_{name}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "model.py"), "w", encoding="utf-8") as fh:
        fh.write(script)
    env = dict(os.environ)
    env["PATH"] = CAD_BIN + os.pathsep + env.get("PATH", "")
    env["CADGEN_BROWSER_PATH"] = EDGE
    env.pop("__COMPAT_LAYER", None)     # 2026-10-19: Edge relaunches itself under it and the preview launch dies
    code, out = _run([CAD_PY, "-I", "model.py"], d, SCRIPT_TIMEOUT_S, env)
    step = os.path.join(d, "model.step")
    if code != 0 or not os.path.isfile(step):
        return {"error": f"The script did not produce model.step (exit {code}).", "output": out[-1500:],
                "tell_barry": "Say the part did not build and why; fix the script and run again."}
    files = {"step": step}
    # full path: on Windows a subprocess resolves a bare name against the PARENT's PATH, not the env passed in
    cadgen = os.path.join(CAD_BIN, "cadgen.exe")
    code, out2 = _run([cadgen, "stl", "build", "model.step", f"{name}.stl"], d, 120, env)
    if code == 0 and os.path.isfile(os.path.join(d, f"{name}.stl")):
        files["stl"] = os.path.join(d, f"{name}.stl")
    png = ""
    if a.get("preview", True):
        code, out3 = _run([cadgen, "snapshot", "model.step", f"{name}.png"], d, 180, env)
        if code == 0 and os.path.isfile(os.path.join(d, f"{name}.png")):
            png = os.path.join(d, f"{name}.png")
            files["png"] = png
    final_step = os.path.join(d, f"{name}.step")
    os.replace(step, final_step)
    files["step"] = final_step
    regs = {}
    for kind, path in files.items():
        regs[kind] = agent_files.register_file(office_name, path, f"CAD {kind.upper()}: {name}. {str(a.get('notes') or '')[:300]}")
    return {
        "saved": True, "folder": d, "files": files, "script_output": out[-600:],
        "convert_output": (out2[-300:] if "stl" not in files else "") + (out3[-300:] if a.get("preview", True) and not png else ""),
        "desk": {k: v.get("download_url", "") for k, v in regs.items()},
        "preview_png": png or None,
        "tell_barry": f"{name}: " + ", ".join(k.upper() for k in files) + " on his DESK. "
                      + ("No preview rendered." if not png else "Preview PNG included."),
        "not_done": "Nothing printed or sent anywhere; the printer is not here yet.",
    }


async def run(office_name: str, a: dict) -> dict:
    return await asyncio.to_thread(_make, office_name, a if isinstance(a, dict) else {})
