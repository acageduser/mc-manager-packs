from __future__ import annotations
import zipfile, hashlib, time, os
from pathlib import Path
from typing import Iterable, Tuple
from .config import settings
from .minecraft import NEVER_TOUCH

DEFAULT_INCLUDE = [
    "config", "journeymap", "libraries", "mods", "resourcepacks", "shaderpacks",
    "options.txt", "optionsof.txt", "optionsshaders.txt", "servers.dat"
]

def _iter_paths(base: Path, entries: Iterable[str]):
    for ent in entries:
        p = base / ent
        if p.is_dir():
            for sub in p.rglob("*"):
                if sub.is_file():
                    yield sub, sub.relative_to(base)
        elif p.is_file():
            yield p, p.relative_to(base)

def build_pack(include: Iterable[str] = DEFAULT_INCLUDE, out_dir: Path | None = None) -> Tuple[Path, dict, Path]:
    mc = Path(settings.minecraft_path)
    out = Path(out_dir or Path.home() / "Documents" / "mc-manager-out")
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / "minecraft-pack.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for file_path, rel in _iter_paths(mc, include):
            top = str(rel).split(os.sep)[0]
            if top in NEVER_TOUCH:
                continue
            z.write(file_path, arcname=str(rel))

    # sha256
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    sha = h.hexdigest()

    manifest = {
        "version": time.strftime("%Y.%m.%d.%H%M"),
        "asset": "minecraft-pack.zip",
        "sha256": sha,
        "paths": [{"path": p, "mode": "replace"} for p in include],
    }
    manifest_path = out / "manifest.json"
    import json
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return zip_path, manifest, manifest_path

def backup_worlds_only(out_dir: Path | None = None) -> Path:
    mc = Path(settings.minecraft_path)
    saves = mc / "saves"
    out = Path(out_dir or Path.home() / "Documents" / "mc-manager-backups")
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    zip_path = out / f"worlds_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if saves.exists():
            for sub in saves.rglob("*"):
                if sub.is_file():
                    z.write(sub, arcname=str(sub.relative_to(saves.parent)))
    return zip_path
