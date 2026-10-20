r"""THE UPDATE THING, MADE REAL (Barry, 2026-09-06: "i need the update thing on
my build to actually work").

What existed before: update_checker.py compared ONE model (config's 9b) and
the Ollama app against their sources, and the dashboard button dumped the
raw JSON in a toast. Nothing could be applied from it, and the engines this
office actually runs on (Bonsai, ComfyUI on D:, its custom nodes, the other
two Ollama models) were never looked at.

This module:
  1. INVENTORIES every updatable component of the build, as ITEMS;
  2. CHECKS each one against its own source (registry digest, GitHub
     release, git remote, PyPI) -- read-only, no download, no install;
  3. APPLIES an update to ONE item when Barry clicks -- and only then. The
     12h background check and the button's "check" never install anything;
     his click is the explicit go (his standing rule since the first
     version: "notify me, I want to choose when to pull an update").

Items (id -> what "update" does):
  ollama-app            Ollama app version vs GitHub latest. NO automatic
                        apply: the office runs AMD's AI Bundle build from a
                        fixed path, and the ollama.com installer lands
                        somewhere else, so it is a manual step -- says so.
  ollama-model:<name>   every pulled model, local digest vs registry HEAD.
                        apply = `ollama pull <name>` (streams progress).
  comfyui               D:\ComfyUI25 git HEAD vs origin. apply = stop the
                        server, `git pull --ff-only`, re-install its
                        requirements with the torch lines STRIPPED (a stock
                        `pip install -r` would swap the ROCm build for a CUDA
                        one -- the 09-03 install rule), then re-check the two
                        local patches an update is known to wipe.
  comfy-node:<name>     each git custom node. apply = pull (+ requirements).
  backend-deps          `pip list --outdated` in the office venv. apply is
                        per package (item id `pip:<name>`), torch family
                        refused.
  bonsai-server         informational: the PrismML llama.cpp fork has no
                        version feed we can read. Listed so it is not
                        forgotten, never "up to date" by silence.

Jobs: one at a time, run in a thread, log kept in memory + data/updates.log.
Refuses to touch ComfyUI while a render holds the GPU.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import subprocess
import sys
import threading
import time

import httpx

from config import COMFY_DIR, COMFY_PYTHON, OLLAMA_HOST

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_DATA = os.path.join(_ROOT, "data")
_STATE_PATH = os.path.join(_DATA, "updates_state.json")
_LOG_PATH = os.path.join(_DATA, "updates.log")
_OFFICE_PYTHON = sys.executable

# The AMD AI Bundle build -- THE reason 14B models run at 40+ tok/s here.
# The ollama.com installer would install a different binary elsewhere; the
# launchers and watchdog start THIS path, so "update the app" is a manual
# AMD-bundle step, never something this module runs.
OLLAMA_EXE = os.getenv("OLLAMA_EXE") or os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "AMD", "AI_Bundle", "Ollama", "ollama.exe")
if not os.path.isfile(OLLAMA_EXE):
    OLLAMA_EXE = "ollama"          # PATH fallback

# Packages an update job must never touch: the ROCm torch build is hand
# installed and a plain upgrade replaces it with a CUDA wheel.
_PIP_DENY = {"torch", "torchvision", "torchaudio", "pytorch-triton-rocm", "triton"}
_TORCH_LINE_RE = re.compile(r"^\s*(torch|torchvision|torchaudio|triton)\b", re.I)

# Local patches a ComfyUI / node update is KNOWN to wipe (both on record in
# CLAUDE.md). After every pull these are re-checked and reported loudly.
_PATCH_MARKERS = [
    (os.path.join(COMFY_DIR, "comfy_extras", "nodes_train.py"), "LOCAL PATCH",
     "gradient-clip patch in nodes_train.py (LoRA training fries without it)"),
    (os.path.join(COMFY_DIR, "custom_nodes", "ComfyUI-GGUF", "loader.py"), "LTXV_BF16_PARAMETERS",
     "ComfyUI-GGUF gemma4 / LTX-2.5 audio patch in loader.py (silent clips without it)"),
]

_lock = threading.Lock()
_state: dict = {"checked_at": None, "items": [], "error": None, "online": None}
_jobs: list[dict] = []
_job_thread: threading.Thread | None = None


# ---------------------------------------------------------------- helpers ---
def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _log(line: str) -> None:
    try:
        os.makedirs(_DATA, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{_now()} {line}\n")
    except OSError:
        pass


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 120,
         env: dict | None = None) -> tuple[int, str]:
    """Run a command, return (rc, combined output). Never raises."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s: {' '.join(cmd)}"
    except OSError as e:
        return 127, f"could not run {cmd[0]}: {e}"


def _is_git(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".git"))


def _git_default_branch(path: str) -> str:
    rc, out = _run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=path, timeout=20)
    if rc == 0 and out.strip():
        return out.strip().split("/", 1)[-1]
    rc, out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path, timeout=20)
    return out.strip() if rc == 0 and out.strip() and out.strip() != "HEAD" else "master"


def _save_state() -> None:
    try:
        os.makedirs(_DATA, exist_ok=True)
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, indent=1)
        os.replace(tmp, _STATE_PATH)
    except OSError as e:
        _log(f"state save failed: {e}")


def _load_state() -> None:
    global _state
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "items" in data:
            _state = data
    except (OSError, ValueError):
        pass


_load_state()


def _item(id_: str, kind: str, name: str, current: str | None, latest: str | None,
          update_available: bool, can_apply: bool, how: str = "", note: str = "",
          detail: str = "", error: str | None = None) -> dict:
    return {"id": id_, "kind": kind, "name": name, "current": current, "latest": latest,
            "update_available": bool(update_available), "can_apply": bool(can_apply),
            "how": how, "note": note, "detail": detail, "error": error}


# ----------------------------------------------------------------- checks ---
def _check_ollama(client: httpx.Client) -> list[dict]:
    items: list[dict] = []
    local_ver, models = None, []
    try:
        local_ver = client.get(f"{OLLAMA_HOST}/api/version", timeout=5).json().get("version")
    except Exception as e:  # noqa: BLE001
        items.append(_item("ollama-app", "app", "Ollama app", None, None, False, False,
                           error=f"Ollama not reachable at {OLLAMA_HOST}: {e}"))
        return items
    try:
        models = client.get(f"{OLLAMA_HOST}/api/tags", timeout=5).json().get("models", [])
    except Exception as e:  # noqa: BLE001
        items.append(_item("ollama-models", "model", "Ollama models", None, None, False, False,
                           error=f"could not list models: {e}"))

    latest, err = None, None
    try:
        r = client.get("https://api.github.com/repos/ollama/ollama/releases/latest", timeout=10)
        r.raise_for_status()
        latest = (r.json().get("tag_name") or "").lstrip("v") or None
    except Exception as e:  # noqa: BLE001
        err = f"could not read the Ollama release list: {e}"
    items.append(_item(
        "ollama-app", "app", "Ollama app (AMD AI Bundle build)", local_ver, latest,
        bool(local_ver and latest and local_ver != latest), False,
        how=("MANUAL. This office runs AMD's AI Bundle build of Ollama from "
             f"{OLLAMA_EXE} -- that build is why the 14B models run at 40+ tok/s. "
             "The ollama.com installer would put a different Ollama somewhere else and "
             "the launchers would keep starting this one. Update it through AMD's AI "
             "Bundle / AMD Software, and check the speed after."),
        error=err))

    for m in models:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        local_digest = m.get("digest")
        family, _, tag = name.partition(":")
        tag = tag or "latest"
        repo = family if "/" in family else f"library/{family}"
        remote, rerr = None, None
        try:
            r = client.head(f"https://registry.ollama.ai/v2/{repo}/manifests/{tag}",
                            headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
                            timeout=10)
            r.raise_for_status()
            remote = r.headers.get("ollama-content-digest")
        except Exception as e:  # noqa: BLE001
            rerr = f"registry check failed: {e}"
        avail = bool(local_digest and remote and local_digest != remote)
        items.append(_item(
            f"ollama-model:{name}", "model", name,
            (local_digest or "")[:12] or None, (remote or "")[:12] or None, avail, avail,
            how=f"ollama pull {name} (downloads the new layers; the model keeps working meanwhile)",
            note="", error=rerr))
    return items


def _check_git_repo(path: str, id_: str, kind: str, name: str, extra_note: str = "") -> dict:
    if not os.path.isdir(path):
        return _item(id_, kind, name, None, None, False, False, error=f"not found: {path}")
    if not _is_git(path):
        return _item(id_, kind, name, None, None, False, False,
                     note="not a git checkout -- cannot be checked or updated automatically")
    branch = _git_default_branch(path)
    rc, out = _run(["git", "fetch", "--quiet", "origin"], cwd=path, timeout=90)
    if rc != 0:
        return _item(id_, kind, name, None, None, False, False, error=f"git fetch failed: {out.strip()[:300]}")
    _, head = _run(["git", "rev-parse", "--short", "HEAD"], cwd=path, timeout=20)
    _, remote = _run(["git", "rev-parse", "--short", f"origin/{branch}"], cwd=path, timeout=20)
    _, count = _run(["git", "rev-list", "--count", f"HEAD..origin/{branch}"], cwd=path, timeout=20)
    _, dirty = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=path, timeout=20)
    _, log = _run(["git", "log", "--oneline", "-8", f"HEAD..origin/{branch}"], cwd=path, timeout=20)
    _, when = _run(["git", "log", "-1", "--format=%cs", "HEAD"], cwd=path, timeout=20)
    try:
        behind = int(count.strip() or 0)
    except ValueError:
        behind = 0
    note = extra_note
    if dirty.strip():
        note = (note + " " if note else "") + (
            "LOCAL EDITS PRESENT (the patched files) -- the update keeps them if they "
            "don't collide; if git refuses, the log will say so and nothing changes.")
    return _item(id_, kind, name,
                 f"{head.strip()} ({when.strip()})", f"{remote.strip()} (+{behind} commits)" if behind else remote.strip(),
                 behind > 0, behind > 0,
                 how=f"git pull --ff-only on {branch}, then its requirements (torch lines stripped)",
                 note=note, detail=log.strip()[:1500])


def _check_comfy() -> list[dict]:
    items = [_check_git_repo(
        COMFY_DIR, "comfyui", "app", f"ComfyUI ({COMFY_DIR})",
        extra_note="After an update the two local patches (gradient clip, GGUF gemma4/LTX audio) "
                   "are re-checked and reported.")]
    nodes_dir = os.path.join(COMFY_DIR, "custom_nodes")
    if os.path.isdir(nodes_dir):
        for n in sorted(os.listdir(nodes_dir)):
            p = os.path.join(nodes_dir, n)
            if os.path.isdir(p) and _is_git(p):
                items.append(_check_git_repo(p, f"comfy-node:{n}", "node", f"ComfyUI node: {n}"))
    return items


def _check_backend_deps() -> list[dict]:
    rc, out = _run([_OFFICE_PYTHON, "-m", "pip", "list", "--outdated", "--format=json",
                    "--disable-pip-version-check"], timeout=180)
    if rc != 0:
        return [_item("backend-deps", "deps", "Backend Python packages", None, None, False, False,
                      error=f"pip list --outdated failed: {out.strip()[:300]}")]
    try:
        pkgs = json.loads(out.strip() or "[]")
    except ValueError:
        pkgs = []
    items = []
    for p in pkgs:
        name = p.get("name", "")
        if not name:
            continue
        denied = name.lower() in _PIP_DENY
        items.append(_item(
            f"pip:{name}", "pip", f"python package: {name}", p.get("version"), p.get("latest_version"),
            True, not denied,
            how=f"pip install --upgrade {name} in the office venv, then a backend restart",
            note=("NEVER auto-upgraded: this is the hand-installed ROCm build." if denied else
                  "Upgrading a library can change behaviour -- one at a time, and check the office after.")))
    if not items:
        items.append(_item("backend-deps", "deps", "Backend Python packages", "all current", None, False, False))
    return items


def _check_bonsai() -> dict:
    exe_dir = os.path.join(_ROOT, "tools", "llama-prism", "vulkan")
    exe = os.path.join(exe_dir, "llama-server.exe")
    cur = None
    if os.path.isfile(exe):
        cur = datetime.datetime.fromtimestamp(os.path.getmtime(exe)).strftime("%Y-%m-%d build")
    return _item("bonsai-server", "app", "Bonsai llama-server (PrismML Vulkan fork)", cur, None, False, False,
                 how="MANUAL. No version feed to read; PrismML publishes new builds on their GitHub releases. "
                     "Swap the folder, restart the backend, and re-run the Bonsai gate before trusting it.")


def check(include_pip: bool = True) -> dict:
    """The full read-only check. Blocking (network + git fetch + pip) --
    call it through run_check() from async code."""
    started = time.time()
    items: list[dict] = []
    error = None
    online = True
    try:
        with httpx.Client(follow_redirects=True) as client:
            try:
                client.head("https://registry.ollama.ai/v2/", timeout=6)
            except Exception as e:  # noqa: BLE001
                online = False
                error = f"Could not reach the internet ({e}). Local versions are shown; 'latest' is unknown."
            items.extend(_check_ollama(client))
    except Exception as e:  # noqa: BLE001
        error = f"Ollama check failed: {e}"
    try:
        items.extend(_check_comfy())
    except Exception as e:  # noqa: BLE001
        items.append(_item("comfyui", "app", "ComfyUI", None, None, False, False, error=str(e)))
    if include_pip:
        try:
            items.extend(_check_backend_deps())
        except Exception as e:  # noqa: BLE001
            items.append(_item("backend-deps", "deps", "Backend Python packages", None, None, False, False, error=str(e)))
    items.append(_check_bonsai())

    with _lock:
        _state.update({"checked_at": _now(), "items": items, "error": error, "online": online,
                       "took_s": round(time.time() - started, 1)})
        _save_state()
    n = sum(1 for i in items if i["update_available"])
    _log(f"check: {len(items)} items, {n} updates available, {round(time.time() - started, 1)}s")
    return result()


async def run_check(include_pip: bool = True) -> dict:
    return await asyncio.to_thread(check, include_pip)


def result() -> dict:
    """Last known result + legacy keys the classic dashboard's load-time toast reads."""
    with _lock:
        st = json.loads(json.dumps(_state))
    items = st.get("items", [])
    app = next((i for i in items if i["id"] == "ollama-app"), {})
    from config import OLLAMA_MODEL
    mdl = next((i for i in items if i["id"] == f"ollama-model:{OLLAMA_MODEL}"), {})
    st.update({
        "available": sum(1 for i in items if i.get("update_available")),
        "model_name": OLLAMA_MODEL,
        "model_update_available": bool(mdl.get("update_available")),
        "local_app_version": app.get("current"),
        "latest_app_version": app.get("latest"),
        "app_update_available": bool(app.get("update_available")),
        "jobs": _jobs[-10:],
    })
    return st


def summary_line() -> str:
    """One line for Sophie's system_health."""
    st = result()
    if not st.get("checked_at"):
        return "updates: never checked"
    avail = [i["name"] for i in st["items"] if i.get("update_available")]
    errs = [i["name"] for i in st["items"] if i.get("error")]
    s = f"updates (checked {st['checked_at'][:16]}): {len(avail)} available"
    if avail:
        s += " -- " + ", ".join(avail[:6]) + ("..." if len(avail) > 6 else "")
    if errs:
        s += f"; {len(errs)} could not be checked"
    return s


# ------------------------------------------------------------------ apply ---
def _render_busy() -> bool:
    try:
        import comfy_image
        return comfy_image.render_in_progress()
    except Exception:  # noqa: BLE001
        return False


def _filtered_requirements(path: str) -> str | None:
    """requirements.txt with the torch family stripped (never swap the ROCm build)."""
    if not os.path.isfile(path):
        return None
    lines = [ln for ln in open(path, encoding="utf-8", errors="replace").read().splitlines()
             if not _TORCH_LINE_RE.match(ln)]
    tmp = path + ".office-filtered.txt"
    open(tmp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return tmp


def _job_log(job: dict, line: str) -> None:
    job["log"].append(line.rstrip()[:400])
    if len(job["log"]) > 400:
        del job["log"][:100]
    _log(f"[job {job['id']} {job['item']}] {line.rstrip()[:300]}")


def _stream(job: dict, cmd: list[str], cwd: str | None = None, timeout: int = 3600,
            env: dict | None = None) -> int:
    """Run a command streaming its output into the job log. Returns rc."""
    _job_log(job, "$ " + " ".join(cmd))
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", env=env, bufsize=1)
    except OSError as e:
        _job_log(job, f"could not start: {e}")
        return 127
    deadline = time.time() + timeout
    last = ""
    assert p.stdout is not None
    for line in p.stdout:
        line = line.replace("\r", "\n").strip()
        if line and line != last:
            _job_log(job, line)
            last = line
        if time.time() > deadline:
            p.kill()
            _job_log(job, f"killed: exceeded {timeout}s")
            return 124
    return p.wait()


def _apply_ollama_pull(job: dict, name: str) -> bool:
    env = dict(os.environ)
    env.setdefault("OLLAMA_HOST", OLLAMA_HOST.replace("http://", "").replace("https://", ""))
    rc = _stream(job, [OLLAMA_EXE, "pull", name], timeout=3 * 3600, env=env)
    return rc == 0


def _apply_git_pull(job: dict, path: str, name: str, is_comfy_root: bool) -> bool:
    if _render_busy():
        _job_log(job, "REFUSED: a render holds the GPU right now. Try again when it finishes.")
        return False
    if is_comfy_root:
        _job_log(job, "stopping the office ComfyUI server so the new code loads on the next render")
        try:
            import comfy_image
            asyncio.run(comfy_image.stop_server())
        except Exception as e:  # noqa: BLE001
            _job_log(job, f"(stop_server: {e})")
    branch = _git_default_branch(path)
    _, before = _run(["git", "rev-parse", "--short", "HEAD"], cwd=path, timeout=20)
    _job_log(job, f"{name}: at {before.strip()} on {branch}")
    if _stream(job, ["git", "pull", "--ff-only", "origin", branch], cwd=path, timeout=300) != 0:
        _job_log(job, "git pull refused -- nothing changed. (Local edits colliding? see the lines above.)")
        return False
    _, after = _run(["git", "rev-parse", "--short", "HEAD"], cwd=path, timeout=20)
    _job_log(job, f"{name}: now at {after.strip()} (rollback: git -C \"{path}\" reset --hard {before.strip()})")
    req = _filtered_requirements(os.path.join(path, "requirements.txt"))
    if req:
        _job_log(job, "installing its requirements (torch family stripped so the ROCm build stays)")
        rc = _stream(job, [COMFY_PYTHON, "-m", "pip", "install", "-r", req, "--disable-pip-version-check"],
                     cwd=path, timeout=1800)
        if rc != 0:
            _job_log(job, "pip had errors -- the code is updated but a package may be missing; read the lines above.")
    ok = True
    if is_comfy_root or "ComfyUI-GGUF" in path:
        for fpath, marker, what in _PATCH_MARKERS:
            if not os.path.isfile(fpath):
                continue
            present = marker in open(fpath, encoding="utf-8", errors="replace").read()
            _job_log(job, ("patch still present: " if present else "!! PATCH WIPED BY THE UPDATE: ") + what)
            if not present:
                ok = False
                _job_log(job, "   -> needs re-applying before the next LoRA training / LTX-2.5 render. "
                              "Ask Sophie or Claude; the recipe is in CLAUDE.md.")
    return ok


def _apply_pip(job: dict, pkg: str) -> bool:
    if pkg.lower() in _PIP_DENY:
        _job_log(job, f"REFUSED: {pkg} is the hand-installed ROCm build family.")
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.\-]+", pkg):
        _job_log(job, "REFUSED: not a plain package name.")
        return False
    _, before = _run([_OFFICE_PYTHON, "-m", "pip", "show", pkg], timeout=60)
    ver = next((ln.split(":", 1)[1].strip() for ln in before.splitlines() if ln.startswith("Version:")), "?")
    rc = _stream(job, [_OFFICE_PYTHON, "-m", "pip", "install", "--upgrade", pkg, "--disable-pip-version-check"],
                 timeout=900)
    if rc == 0:
        _job_log(job, f"done. Rollback: pip install {pkg}=={ver}. Restart the backend to load it "
                      "(kill the process; the watchdog revives it).")
    return rc == 0


def _run_job(job: dict) -> None:
    job["status"] = "running"
    job["started_at"] = _now()
    ok = False
    try:
        iid = job["item"]
        if iid.startswith("ollama-model:"):
            ok = _apply_ollama_pull(job, iid.split(":", 1)[1])
        elif iid == "comfyui":
            ok = _apply_git_pull(job, COMFY_DIR, "ComfyUI", True)
        elif iid.startswith("comfy-node:"):
            ok = _apply_git_pull(job, os.path.join(COMFY_DIR, "custom_nodes", iid.split(":", 1)[1]),
                                 iid.split(":", 1)[1], False)
        elif iid.startswith("pip:"):
            ok = _apply_pip(job, iid.split(":", 1)[1])
        else:
            _job_log(job, "this item is manual -- see its 'how'.")
    except Exception as e:  # noqa: BLE001
        _job_log(job, f"job crashed: {e}")
    job["status"] = "done" if ok else "failed"
    job["finished_at"] = _now()
    _log(f"job {job['id']} {job['item']}: {job['status']}")
    # Re-check just this item's family so the panel shows the new state.
    try:
        check(include_pip=job["item"].startswith("pip:"))
    except Exception as e:  # noqa: BLE001
        _log(f"post-job re-check failed: {e}")


def apply(item_id: str) -> dict:
    """Start an update job for one item. Barry's click is the only caller."""
    global _job_thread
    with _lock:
        item = next((i for i in _state.get("items", []) if i["id"] == item_id), None)
    if item is None:
        return {"status": "refused", "why": f"unknown item {item_id!r} -- run a check first"}
    if not item.get("can_apply"):
        return {"status": "refused", "why": item.get("how") or "this item cannot be updated from here"}
    if _job_thread is not None and _job_thread.is_alive():
        return {"status": "refused", "why": "another update is still running -- one at a time"}
    if item_id.startswith(("comfyui", "comfy-node:")) and _render_busy():
        return {"status": "refused", "why": "a render holds the GPU right now -- try again when it finishes"}
    job = {"id": (max([j["id"] for j in _jobs], default=0) + 1), "item": item_id, "name": item["name"],
           "status": "queued", "log": [], "started_at": None, "finished_at": None}
    _jobs.append(job)
    if len(_jobs) > 30:
        del _jobs[:10]
    _job_thread = threading.Thread(target=_run_job, args=(job,), daemon=True, name=f"update-{job['id']}")
    _job_thread.start()
    return {"status": "started", "job": job["id"], "name": item["name"]}


def jobs() -> list[dict]:
    return _jobs[-10:]
