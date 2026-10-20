"""
Checks whether a newer version of the configured Ollama model, or the
Ollama app itself, is available -- and ONLY checks. Nothing in this file
ever downloads or installs anything; that stays a deliberate step the
owner takes themselves (e.g. `ollama pull <model>`, or grabbing a new
Ollama installer from ollama.com). See main.py for the periodic background
task that calls run_check(), and /api/updates for how Godot reads the
result (shown in the projection screen's Settings tab).

Both checks are read-only, no-download HTTP calls:
  - Model update: compares the locally-installed model's digest (from
    Ollama's own local /api/tags) against the public registry's manifest
    digest -- fetched via a plain GET with an Accept header that returns
    just the manifest (and a digest response header), not the actual model
    weights. No layers are pulled.
  - App update: compares the locally-running Ollama version (local
    /api/version) against the latest tagged release on GitHub.
"""
import datetime

import httpx

from config import OLLAMA_HOST, OLLAMA_MODEL

_last_check_result = {
    "checked_at": None,
    "online": False,
    "model_name": OLLAMA_MODEL,
    "local_model_digest": None,
    "remote_model_digest": None,
    "model_update_available": False,
    "local_app_version": None,
    "latest_app_version": None,
    "app_update_available": False,
    "error": None,
}


async def run_check() -> dict:
    result = dict(_last_check_result)
    result["checked_at"] = datetime.datetime.now(datetime.UTC).isoformat()
    result["error"] = None

    async with httpx.AsyncClient(timeout=10.0) as client:
        # --- local Ollama state -- independent of internet access ---
        try:
            tags_resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            tags_resp.raise_for_status()
            for m in tags_resp.json().get("models", []):
                if m.get("name") == OLLAMA_MODEL or m.get("model") == OLLAMA_MODEL:
                    result["local_model_digest"] = m.get("digest")
                    break
        except httpx.HTTPError:
            pass

        try:
            ver_resp = await client.get(f"{OLLAMA_HOST}/api/version")
            ver_resp.raise_for_status()
            result["local_app_version"] = ver_resp.json().get("version")
        except httpx.HTTPError:
            pass

        # --- remote checks -- only meaningful if actually online ---
        try:
            family, _, tag = OLLAMA_MODEL.partition(":")
            tag = tag or "latest"
            # "library/" is the namespace for OFFICIAL Ollama models only
            # (llama3 -> /v2/library/llama3). A community model already
            # carries its own namespace (huihui_ai/qwen3.5-abliterated ->
            # /v2/huihui_ai/qwen3.5-abliterated), and prefixing library/ onto
            # it produced a hard 404 on every single check -- which this
            # office noticed as a permanent "update check failed" banner,
            # because EVERY model it runs is namespaced. Verified 2026-08-11:
            # .../v2/library/huihui_ai/... -> 404, .../v2/huihui_ai/... -> 200
            # with the ollama-content-digest header present.
            repo = family if "/" in family else f"library/{family}"
            manifest_url = f"https://registry.ollama.ai/v2/{repo}/manifests/{tag}"
            # HEAD, not GET -- the registry only returns the digest as a
            # response header on HEAD (standard OCI/Docker registry
            # behavior for "check without downloading"); GET returns the
            # actual manifest body instead and no digest header.
            manifest_resp = await client.head(
                manifest_url,
                headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"},
            )
            manifest_resp.raise_for_status()
            remote_digest = manifest_resp.headers.get("ollama-content-digest")
            result["remote_model_digest"] = remote_digest
            result["model_update_available"] = bool(
                result["local_model_digest"]
                and remote_digest
                and result["local_model_digest"] != remote_digest
            )

            release_resp = await client.get(
                "https://api.github.com/repos/ollama/ollama/releases/latest"
            )
            release_resp.raise_for_status()
            latest_tag = release_resp.json().get("tag_name", "").lstrip("v")
            result["latest_app_version"] = latest_tag
            result["app_update_available"] = bool(
                result["local_app_version"]
                and latest_tag
                and result["local_app_version"] != latest_tag
            )

            result["online"] = True
        except httpx.HTTPStatusError as e:
            # We DID reach the internet -- the server answered, just not with
            # what we wanted. Reporting this as "could not reach the internet"
            # is what disguised the library/ URL bug above as a connectivity
            # problem for weeks. Say what actually happened, and do NOT claim
            # to be offline.
            result["online"] = True
            result["error"] = (
                f"Reached the update server but it refused the request "
                f"(HTTP {e.response.status_code} for {e.request.url}). "
                f"This is a bad request on our side, not a connection problem."
            )
        except httpx.HTTPError as e:
            # Genuinely unreachable -- no internet, DNS, timeout. Routine,
            # not worth erroring loudly over. Local info (if we got any) is
            # kept; only the "is there something newer" answer is stale.
            result["online"] = False
            result["error"] = f"Could not reach the internet to check for updates: {e}"

    _last_check_result.clear()
    _last_check_result.update(result)
    return result
