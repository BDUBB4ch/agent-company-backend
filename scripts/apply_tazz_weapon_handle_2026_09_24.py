"""Tazz's weapon handle -> @missle-launcher (Barry, 2026-09-24: "@missle-launcher
is her weapon name. make sure elliot knows too").

Edits BOTH canon copies (data/barry-character-canon.md + fact 592) identically.
Only the ACTIVE handle lines change; a dated ruling block records the rename and
keeps @Tazz's-Weapon on record as retired (never sweep the record). Every replace
is asserted to hit exactly once. Refuses to run twice.
"""
import io, os, sqlite3, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
import memory  # noqa: E402

DISK = os.path.join(ROOT, "data", "barry-character-canon.md")

RULING = (
    "--- TAZZ'S WEAPON HANDLE, RENAMED (Barry 2026-09-24) ---\n"
    "His words, verbatim: \"@missle-launcher is her weapon name. make sure elliot\n"
    "knows too\". THE ONLY HANDLE FOR TAZZ'S WEAPON IS @missle-launcher -- spelled\n"
    "exactly that way (\"missle\", as he wrote it; it is the string his asset is\n"
    "bound to). @Tazz's-Weapon is RETIRED; where an older file says it, you type\n"
    "@missle-launcher. The weapon itself is unchanged: the two-handed hot-pink\n"
    "mini missile blaster, carried across her back on its magnetic mount.\n\n"
)

REPLACES = [
    ("  @Tazz's-Weapon            Tazz's missile-cluster weapon\n",
     "  @missle-launcher          Tazz's missile-cluster weapon (@Tazz's-Weapon RETIRED 2026-09-24)\n"),
    ("NOT RENAMED, so do not change them: @keth and @lady-vor-shara-vel.\n",
     "NOT RENAMED, so do not change them: @keth and @lady-vor-shara-vel.\n\n" + RULING.rstrip("\n") + "\n"),
    ("  @Tazz's-Weapon             -> locally: \"her two-handed missile blaster\"\n",
     "  @missle-launcher           -> locally: \"her two-handed missile blaster\"\n"),
    ("  Tazz           @Tazz           two-handed missile weapon   @Tazz's-Weapon\n",
     "  Tazz           @Tazz           two-handed missile weapon   @missle-launcher\n"),
    ("  handle instead: @Bia's-Pistol*, @Yannah's-Machine-Pistol, @Tazz's-Weapon.\n",
     "  handle instead: @Bia's-Pistol*, @Yannah's-Machine-Pistol, @missle-launcher.\n"
     "  Where it says @Tazz's-Weapon, you type @missle-launcher.\n"),
]


def apply(text):
    if "TAZZ'S WEAPON HANDLE, RENAMED" in text:
        raise SystemExit("already applied")
    for old, new in REPLACES:
        n = text.count(old)
        assert n == 1, f"expected 1 hit, got {n}: {old!r}"
        text = text.replace(old, new)
    return text


disk = io.open(DISK, encoding="utf-8").read()
c = sqlite3.connect(memory.DB_PATH)
fact = c.execute("select content from facts where id=592").fetchone()[0]
assert disk == fact, "canon copies differ -- diff them before syncing"

stamp = time.strftime("%Y%m%d_%H%M%S")
for name, body in (("disk", disk), ("fact592", fact)):
    io.open(os.path.join(ROOT, "data", f"backup_{name}_canon_before_tazz_handle_{stamp}.md"),
            "w", encoding="utf-8").write(body)

new = apply(disk)
io.open(DISK, "w", encoding="utf-8").write(new)
c.execute("update facts set content=? where id=592", (new,))
c.commit()
back = c.execute("select content from facts where id=592").fetchone()[0]
assert back == io.open(DISK, encoding="utf-8").read() == new
print("ok", len(disk), "->", len(new), "| both copies identical")
