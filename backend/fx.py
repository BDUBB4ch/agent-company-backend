"""EFFECTS for Ilnora's videos (2026-10-19, Barry: "Push the visuals. Sparks, lightning, purple smoke, glowing sigils,
whatever dark-magic effects you can throw at it. Make it feel like a ritual, not just a talking-head video" and "do the
effects stuff i was saying earlier").

A part carries "fx": a list of names. Two kinds, both on the CPU, no card time:
  GRADES (ffmpeg on the finished clip): ritual (darker night, a little less colour, contrast, grain, vignette -- no cast), blood
    (red push, crushed blacks), cold (dead blue), flicker (candle-light breathing), glow (bloom on the highlights),
    grain, vignette.
  LAYERS (one Hyperframes render on black per part, data/video_queue/cards/fx_overlay.html, screen-blended over the
    clip so black changes nothing): smoke (grey-white), embers, sparks, lightning, sigil (HER OWN drawing -- the part's
    "sigil": SVG paths in a 0-100 box -- drawn in light stroke by stroke, for a spell she is casting; a sigil ON something
    is written into her shot so the picture engine draws it on the surface). Barry 10-19: "the sigils should be
    something she creates, not something thats seeded" -- no ready-made sigils exist here.
This is the technique the published ComfyUI VFX workflows use (blur + screen for glow, effects on black screened over
the shot); done here in the builder so it costs no GPU and never touches her words. A failed effect logs and leaves the
clip as it was -- an effect never kills her video.
"""
from __future__ import annotations

import json
import os
import shutil

GRADES = ("ritual", "blood", "cold", "flicker", "glow", "grain", "vignette")
LAYERS = ("smoke", "embers", "sparks", "lightning", "sigil")
SIGIL_AT = ("top", "center", "bottom", "left", "right")
_PATH_OK = __import__("re").compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9eE .,\-]{3,4000}$")
ALL = GRADES + LAYERS

_GRADE_FILTERS = {
    "ritual": "eq=contrast=1.12:saturation=0.85:gamma=0.88:brightness=-0.03",   # night, NO colour cast (Barry 10-19: no purple haze)
    "blood": "colorbalance=rs=0.18:gs=-0.05:bs=-0.07:rm=0.12:gm=-0.04:bm=-0.05,eq=contrast=1.2:saturation=0.9:gamma=0.8:brightness=-0.04",
    "cold": "colorbalance=rs=-0.07:bs=0.12:rm=-0.06:bm=0.09,eq=contrast=1.1:saturation=0.5:gamma=0.85:brightness=-0.04",
    "flicker": "eq=brightness='0.035*sin(2*PI*t*6.3)+0.022*sin(2*PI*t*13.7)+0.012*sin(2*PI*t*23.1)':eval=frame",
}
_ORDER = ("ritual", "blood", "cold", "flicker")
PRE_S = 4.0       # pre-roll rendered and cut off, so smoke and embers are already moving at the first frame


def parse(fx) -> tuple[list[str], str | None]:
    """Her fx list -> (known names in order, the first unknown name or None)."""
    items = [fx] if isinstance(fx, str) else (fx if isinstance(fx, list) else [])
    out, bad = [], None
    for raw in items:
        name = " ".join(str(raw or "").lower().split()).replace(" ", "")
        if not name:
            continue
        base, _, kind = name.partition(":")
        if base not in ALL or kind:
            bad = bad or str(raw)
            continue
        if name not in out:
            out.append(name)
    return out, bad


def sigil_paths(paths) -> tuple[list[str], str | None]:
    """Her sigil drawing: SVG path strings in a 0-100 box. (clean list, first bad one or None)."""
    items = [paths] if isinstance(paths, str) else (paths if isinstance(paths, list) else [])
    out = []
    for p in items[:24]:
        p = " ".join(str(p or "").split())
        if not p:
            continue
        if not _PATH_OK.match(p) or p[0] not in "Mm":
            return out, p[:60]
        out.append(p)
    return out, None


def _overlay_project(names: list[str], seconds: float, fmt: dict, d: str, idx: int, mode: str = "draw",
                     sigil: list | None = None, sigil_at: str = "center") -> str | None:
    import reel_builder
    layers = sorted({n.partition(":")[0] for n in names if n.partition(":")[0] in LAYERS})
    if not layers:
        return None
    proj = os.path.join(d, f"fx{idx:03d}{mode[0]}")
    os.makedirs(proj, exist_ok=True)
    vendor = os.path.join(proj, "vendor")
    if not os.path.isdir(vendor):
        shutil.copytree(os.path.join(reel_builder.CARDS_DIR, "vendor"), vendor)
    page = (open(os.path.join(reel_builder.CARDS_DIR, "fx_overlay.html"), encoding="utf-8").read()
            .replace("{{W}}", str(fmt["w"])).replace("{{H}}", str(fmt["h"]))
            .replace("{{SECONDS}}", f"{seconds + PRE_S:.2f}").replace("{{PRE}}", f"{PRE_S:.1f}")
            .replace("{{LAYERS}}", json.dumps(layers))
            .replace("{{SIGIL_PATHS}}", json.dumps(sigil_paths(sigil or [])[0]))
            .replace("{{SIGIL_AT}}", sigil_at if sigil_at in SIGIL_AT else "center").replace("{{MODE}}", mode).replace("{{SEED}}", str(1000 + idx * 7919)))
    with open(os.path.join(proj, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    with open(os.path.join(proj, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump({"id": f"fx{idx:03d}{mode[0]}", "name": f"effects {mode} " + "+".join(layers)}, fh)
    return proj


def _graph(names: list[str], has_layer: bool, fmt: dict) -> str:
    import reel_builder
    W, H = fmt["w"], fmt["h"]
    plain = [_GRADE_FILTERS[g] for g in _ORDER if g in names]
    if "grain" in names or "ritual" in names:
        plain.append("noise=alls=7:allf=t")
    if "vignette" in names or "ritual" in names or "blood" in names:
        plain.append("vignette=angle=PI/3.6")
    g = f"[0:v]{','.join(plain) if plain else 'null'}[g0]"
    cur = "g0"
    if "glow" in names or "ritual" in names:
        g += (f";[{cur}]format=gbrp,split[ga][gb];[gb]curves=all='0/0 0.62/0.02 1/1',gblur=sigma=26[gc];"
              f"[ga][gc]blend=all_mode=screen:all_opacity={0.7 if 'glow' in names else 0.4}[g1]")
        cur = "g1"
    if has_layer:
        # LIGHT FALLS ON THINGS (Barry 2026-10-19: "if there is a glow, it should show up as a reflection on something
        # where it makes sence, not just in the air"). The light pass is blurred into a light map and MULTIPLIED onto
        # the picture, then added: a lit surface near the effect (her face, the gown, stone, the brazier) picks up its
        # light and colour in proportion to how lit it already is; empty dark air gets nothing. Only the drawn lines,
        # bolts and sparks themselves are screened on top.
        sig = max(40, round(min(W, H) * 0.11))
        pad = f"scale={W}:{H},fps={reel_builder.FPS},tpad=stop_mode=clone:stop_duration=2,format=gbrp"
        g += (f";[2:v]{pad},gblur=sigma={sig},eq=brightness=0.0:contrast=1.0[lm];"
              f"[{cur}]format=gbrp,split[pa][pb];[pa][lm]blend=all_mode=multiply[lit];"
              f"[pb][lit]blend=all_mode=addition[relit];"
              f"[1:v]{pad}[ov];[relit][ov]blend=all_mode=screen[g2]")
        cur = "g2"
    return g + f";[{cur}]format=yuv420p[v]"


def apply(clip: str, fx, seconds: float, fmt: dict, d: str, idx: int, log=print, sigil=None, sigil_at: str = "center") -> bool:
    """Run her effects over one finished scene clip, in place. True when applied; never raises."""
    import reel_builder
    d = os.path.abspath(d)          # Hyperframes runs in its own folder: a relative out path lands nowhere
    names, bad = parse(fx)
    if bad:
        log(f"fx (part {idx + 1}): unknown effect {bad!r} skipped")
    if not names or not os.path.isfile(clip):
        return False
    try:
        layer_mp4 = light_mp4 = None
        proj = _overlay_project(names, seconds, fmt, d, idx, "draw", sigil, sigil_at)
        if proj:
            layer_mp4 = os.path.join(d, f"fx{idx:03d}d.mp4")
            light_mp4 = os.path.join(d, f"fx{idx:03d}l.mp4")
            lproj = _overlay_project(names, seconds, fmt, d, idx, "light", sigil, sigil_at)
            if not (reel_builder._card_render(proj, layer_mp4, log) and reel_builder._card_render(lproj, light_mp4, log)):
                log(f"fx (part {idx + 1}): effects layer did not render -- grade only")
                layer_mp4 = light_mp4 = None
        out = clip[:-4] + "_fx.mp4"
        args = ["-i", clip] + (["-ss", f"{PRE_S:.2f}", "-i", layer_mp4, "-ss", f"{PRE_S:.2f}", "-i", light_mp4]
                               if layer_mp4 else [])
        reel_builder._run(args + ["-filter_complex", _graph(names, bool(layer_mp4), fmt), "-map", "[v]", "-an",
                                  "-t", f"{seconds:.3f}", "-r", str(reel_builder.FPS), "-c:v", "libx264",
                                  "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out])
        os.replace(out, clip)
        log(f"fx (part {idx + 1}): {', '.join(names)}")
        return True
    except Exception as exc:  # noqa: BLE001 -- an effect never kills the reel
        log(f"fx (part {idx + 1}) failed, clip kept as it was: {type(exc).__name__}: {str(exc)[:300]}")
        return False
