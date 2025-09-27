#app\services\minecraft.py

import os
import shutil
import zipfile
import time
import json
from typing import Callable, Iterable, Dict, Any, List

from .config import load_settings, save_settings, NEVER_TOUCH


def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def backups_dir() -> str:
    s = load_settings()
    mc = s["minecraft_path"]
    d = os.path.join(mc, "Backups")
    ensure_dir(d)
    return d


def create_backup(label: str, items: Iterable[str], log: Callable[[str], None]) -> str:
    root = backups_dir()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(root, f"{stamp}_{label}")
    ensure_dir(dest)
    s = load_settings()
    mc = s["minecraft_path"]
    for rel in items:
        src = os.path.join(mc, rel)
        if not os.path.exists(src):
            continue
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, target, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(src, target)
        log(f"[BACKUP] {rel}")
    return dest


def prune_backups(keep_n: int, log: Callable[[str], None]):
    d = backups_dir()
    entries = [os.path.join(d, x) for x in os.listdir(d)]
    entries = [x for x in entries if os.path.isdir(x)]
    entries.sort(reverse=True)  # newest first (lexicographic stamp)
    for extra in entries[keep_n:]:
        shutil.rmtree(extra, ignore_errors=True)
        log(f"[PRUNE] {os.path.basename(extra)}")


def safe_rel(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def apply_manifest(extract_dir: str, manifest: Dict[str, Any], dry_run: bool, log: Callable[[str], None]):
    s = load_settings()
    mc = s["minecraft_path"]
    to_replace: List[str] = [safe_rel(p["path"]) for p in manifest.get("paths", [])]
    to_replace = [p for p in to_replace if p.split("/")[0] not in NEVER_TOUCH]

    create_backup("pre_update", to_replace, log)

    for rel in to_replace:
        src = os.path.join(extract_dir, rel)
        dst = os.path.join(mc, rel)
        log(f"[REPLACE] {rel}")
        if dry_run:
            continue
        if os.path.exists(dst):
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            else:
                try:
                    os.remove(dst)
                except Exception:
                    pass
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)

    if not dry_run:
        s["last_applied_version"] = manifest.get("version", "")
        save_settings(s)
        prune_backups(int(s.get("keep_backups", 3)), log)


def _gather_files(mc_root: str, rel: str, log: Callable[[str], None]):
    """Yield (abs_path, arcname) for a single file or all files under a folder."""
    rel_clean = safe_rel(rel)
    src = os.path.join(mc_root, rel_clean)
    if not os.path.exists(src):
        log(f"[SKIP missing] {rel_clean}")
        return

    if os.path.isdir(src):
        cnt = 0
        for base, _, files in os.walk(src):
            for f in files:
                cnt += 1
                full = os.path.join(base, f)
                arc = os.path.relpath(full, mc_root).replace("\\", "/")
                yield full, arc
        log(f"[SCAN] {rel_clean} → {cnt} file(s)")
    else:
        yield src, rel_clean
        log(f"[SCAN] {rel_clean} → 1 file")


def build_pack(include_paths, out_dir, log, progress=None):
    """
    Create minecraft-pack.zip with the selected items from .minecraft.
    Returns (zip_path, manifest_path, manifest_dict)
    """
    s = load_settings()
    mc = (s.get("minecraft_path") or "").strip()
    if not mc:
        raise RuntimeError("minecraft_path is empty in settings.")
    if not os.path.isdir(mc):
        raise RuntimeError(f".minecraft path does not exist: {mc}")

    os.makedirs(out_dir, exist_ok=True)
    log(f"[MC ROOT] {mc}")
    log(f"[OUT DIR] {out_dir}")

    # Filter “never touch” at the top-level only
    filtered = []
    for rel in include_paths:
        top = safe_rel(rel).split("/", 1)[0]
        if top in NEVER_TOUCH:
            log(f"[SKIP protected] {rel}")
            continue
        filtered.append(rel)

    if not filtered:
        raise RuntimeError("Selection is empty after filtering protected items.")

    zip_path = os.path.join(out_dir, "minecraft-pack.zip")
    mani_path = os.path.join(out_dir, "manifest.json")

    # Gather files first (so progress is real)
    all_files = []
    for rel in filtered:
        for pair in _gather_files(mc, rel, log):
            all_files.append(pair)

    if not all_files:
        raise RuntimeError("No files resolved from selection.")

    total = len(all_files)
    log(f"[START] Zipping {total} file(s) → {zip_path}")
    if progress:
        progress(0.10)

    # Zip with occasional progress updates
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for i, (full, arc) in enumerate(all_files, start=1):
            z.write(full, arcname=arc)
            if progress and (i % 50 == 0 or i == total):
                progress(0.10 + 0.80 * (i / total))

    # Manifest
    from .github_api import sha256_file
    sha = sha256_file(zip_path)
    manifest = {
        "version": time.strftime("%Y.%m.%d.%H%M"),
        "asset": "minecraft-pack.zip",
        "sha256": sha,
        "paths": [{"path": safe_rel(p), "mode": "replace"} for p in include_paths],
    }
    with open(mani_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    log(f"[SHA256] {sha}")
    log("[DONE] Pack built.")
    if progress:
        progress(0.95)

    return zip_path, mani_path, manifest
