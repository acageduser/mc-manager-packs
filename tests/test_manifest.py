from pathlib import Path
from app.services.packer import build_pack, DEFAULT_INCLUDE
from app.services.config import settings
import json, os

def test_build_pack(tmp_path, monkeypatch):
    # create fake minecraft dir with one file
    mc = tmp_path / ".minecraft" / "config"
    mc.mkdir(parents=True)
    (mc / "a.txt").write_text("hi", encoding="utf-8")
    monkeypatch.setattr(settings, "minecraft_path", str((tmp_path/".minecraft").resolve()))

    zip_path, manifest, manifest_path = build_pack(["config"], out_dir=tmp_path)
    assert zip_path.exists()
    assert manifest_path.exists()
    assert "sha256" in manifest
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["asset"] == "minecraft-pack.zip"
