"""Probe: can the read-only WooCommerce key see /system_status, and does it
carry plugin version_latest fields? Read-only GET, nothing written."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import store  # noqa: E402

try:
    data = store._get("/system_status")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
    sys.exit(1)

plugins = data.get("active_plugins", [])
print(f"ok -- {len(plugins)} active plugins visible")
behind = [p for p in plugins
          if p.get("version") and p.get("version_latest")
          and p["version"] != p["version_latest"]]
print(f"{len(behind)} plugins behind latest:")
for p in behind[:15]:
    print(f"  - {p.get('name','?')}: {p.get('version')} -> {p.get('version_latest')}")
env = data.get("environment", {})
print(f"wp={env.get('wp_version')} wc={env.get('version')}")
db = data.get("database", {})
print(f"keys present: {sorted(k for k in data.keys())[:10]}")
