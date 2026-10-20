r"""Fix Start Everything.bat after the Desktop reorganization broke it.

The .bat resolves everything relative to its own location (%~dp0). It was
moved into Desktop\Launchers on 2026-08-24 without its three sibling project
folders, so BACKEND_DIR/DASHBOARD_DIR pointed inside Launchers\ and the
launcher died with "The current directory is invalid". The watchdog masked
it until the 2026-08-28 reboot. Fix: pin BASE to the real Desktop.
Backup made by the caller first. Asserts the anchor exists exactly once.
"""
BAT = r"C:\Users\Owner\Desktop\Launchers\Start Everything.bat"

old = 'set "BASE=%~dp0"'
new = (
    "REM FIXED 2026-08-28: this .bat was moved into Desktop\\Launchers during\r\n"
    "REM the desktop reorganization, but the three project folders stayed on\r\n"
    "REM the Desktop itself. Resolve there, not relative to this file.\r\n"
    'set "BASE=C:\\Users\\Owner\\Desktop\\"'
)

s = open(BAT, "rb").read().decode("utf-8", "replace")
count = s.count(old)
assert count == 1, f"anchor found {count} times, expected 1 -- aborting"
s = s.replace(old, new)
open(BAT, "wb").write(s.encode("utf-8"))
print("patched OK")
