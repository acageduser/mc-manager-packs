import os
import json
import time
from typing import Dict, Any, Optional, Callable

import requests

from .config import load_settings, get_pat

UA = {"User-Agent": "MinecraftManager/1.0"}

# --------- Helpers ---------
def _token_or_fail() -> str:
    token = os.environ.get("GITHUB_TOKEN") or get_pat()
    if not token:
        raise RuntimeError(
            "GitHub authorization failed (no token). "
            "Save a PAT in Settings → “Save PAT (DPAPI)”, or set GITHUB_TOKEN."
        )
    return token


def _auth_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN") or get_pat()
    base = {
        **UA,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        base["Authorization"] = f"Bearer {token}"
    return base


def _stage(progress: Optional[Callable[[float], None]], value: float):
    if progress:
        progress(max(0.0, min(1.0, value)))


# --------- Read (User tab) ---------
def get_latest_manifest(progress=None, log=None) -> Dict[str, Any]:
    s = load_settings()
    url = f"https://api.github.com/repos/{s['repo_owner']}/{s['repo_name']}/releases/latest"
    r = requests.get(url, headers=_auth_headers(), timeout=60)
    r.raise_for_status()
    rel = r.json()
    assets = rel.get("assets", [])
    mani = next((a for a in assets if a.get("name") == "manifest.json"), None)
    if not mani:
        raise RuntimeError("manifest.json not found in latest release assets.")
    murl = mani["browser_download_url"]
    mr = requests.get(murl, headers=_auth_headers(), timeout=60)
    mr.raise_for_status()
    return mr.json()


def download_asset(asset_name: str, to_dir: str, progress=None, log=None) -> str:
    s = load_settings()
    url = f"https://api.github.com/repos/{s['repo_owner']}/{s['repo_name']}/releases/latest"
    r = requests.get(url, headers=_auth_headers(), timeout=60)
    r.raise_for_status()
    rel = r.json()
    ass = next((a for a in rel.get("assets", []) if a.get("name") == asset_name), None)
    if not ass:
        raise RuntimeError(f"{asset_name} not found in latest release assets.")
    durl = ass["browser_download_url"]

    os.makedirs(to_dir, exist_ok=True)
    out_path = os.path.join(to_dir, asset_name)
    with requests.get(durl, headers=_auth_headers(), stream=True, timeout=600) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", "0") or "0")
        read = 0
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                f.write(chunk)
                read += len(chunk)
                if progress and total:
                    progress(read / total)
    if progress:
        progress(1.0)
    return out_path


def sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


# --------- Publish (Admin tab) ---------
def _release_by_tag(owner: str, repo: str, tag: str) -> Optional[dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    r = requests.get(url, headers=_auth_headers(), timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _create_release(owner: str, repo: str, tag: str, name: str, body: str = "") -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": False,
    }
    r = requests.post(url, headers=_auth_headers(), json=payload, timeout=60)
    r.raise_for_status()
    return r.json()


class _ProgressFile:
    """
    A file-like object that reports read progress to a callback.
    requests will use __len__ for Content-Length automatically.
    """
    def __init__(self, path: str, cb: Optional[Callable[[float], None]], start: float, end: float):
        self._f = open(path, "rb")
        self._total = os.path.getsize(path)
        self._read = 0
        self._cb = cb
        self._start = start
        self._end = end

    def __len__(self):
        return self._total

    def read(self, amt: int = 1024 * 1024):
        chunk = self._f.read(amt)
        if not chunk:
            return b""
        self._read += len(chunk)
        frac_file = (self._read / self._total) if self._total else 1.0
        _stage(self._cb, self._start + (self._end - self._start) * frac_file)
        return chunk

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass


def _upload_asset(
    upload_url_tmpl: str,
    filepath: str,
    asset_name: str,
    content_type: str,
    progress: Optional[Callable[[float], None]] = None,
    start: float = 0.0,
    end: float = 1.0,
):
    """
    Upload an asset to the release, reporting progress from [start, end].
    Uses a file-like object so requests sets Content-Length correctly.
    """
    # upload_url looks like: https://uploads.github.com/.../assets{?name,label}
    upload_url = upload_url_tmpl.split("{", 1)[0] + f"?name={asset_name}"
    heads = {"Content-Type": content_type, **_auth_headers()}

    fp = _ProgressFile(filepath, progress, start, end)
    try:
        r = requests.post(upload_url, headers=heads, data=fp, timeout=600)
    finally:
        fp.close()

    if r.status_code == 422 and "already_exists" in r.text:
        # find & delete existing asset, then re-upload
        rel_meta_url = upload_url_tmpl.split("{", 1)[0]          # .../assets
        rel_meta_url = rel_meta_url.rsplit("/", 1)[0]             # .../releases/<id>
        rel_meta_url = rel_meta_url.replace("uploads.", "api.")
        rel_resp = requests.get(rel_meta_url, headers=_auth_headers(), timeout=60)
        rel_resp.raise_for_status()
        release = rel_resp.json()
        asset = next((a for a in release.get("assets", []) if a.get("name") == asset_name), None)
        if asset:
            requests.delete(asset["url"], headers=_auth_headers(), timeout=60)

        fp2 = _ProgressFile(filepath, progress, start, end)
        try:
            r = requests.post(upload_url, headers=heads, data=fp2, timeout=600)
        finally:
            fp2.close()

    r.raise_for_status()
    _stage(progress, end)
    return r.json()


def publish_pack(
    manifest_path: str,
    zip_path: str,
    log: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[float], None]] = None,
) -> str:
    """
    Ensure a release exists (tag from manifest['version'] or timestamp) and upload:
      - manifest.json
      - minecraft-pack.zip
    Emits progress from 0 → 1 if 'progress' is provided.
    Returns the tag name used.
    """
    _token_or_fail()  # fail fast with a helpful message

    s = load_settings()
    owner, repo = s["repo_owner"], s["repo_name"]

    _stage(progress, 0.02)
    with open(manifest_path, "r", encoding="utf-8") as f:
        mani = json.load(f)
    tag = str(mani.get("version") or time.strftime("%Y.%m.%d.%H%M"))
    name = f"Pack v{tag}"
    if log:
        log(f"[RELEASE] Tag: {tag}")

    _stage(progress, 0.10)
    rel = _release_by_tag(owner, repo, tag)
    if not rel:
        rel = _create_release(owner, repo, tag, name, body="")
        if log:
            log("[RELEASE] Created new release.")
    else:
        if log:
            log("[RELEASE] Using existing release (will replace assets).")

    upload_url = rel["upload_url"]

    # Upload manifest.json: 10% → 35%
    if log:
        log("[UPLOAD] manifest.json")
    _upload_asset(
        upload_url,
        manifest_path,
        "manifest.json",
        "application/octet-stream",  # more reliable for GitHub asset uploads
        progress=progress,
        start=0.10,
        end=0.35,
    )

    # Upload minecraft-pack.zip: 35% → 1.0
    if log:
        log("[UPLOAD] minecraft-pack.zip")
    _upload_asset(
        upload_url,
        zip_path,
        "minecraft-pack.zip",
        "application/zip",
        progress=progress,
        start=0.35,
        end=1.0,
    )

    if log:
        log("[DONE] Published.")
    _stage(progress, 1.0)
    return tag
