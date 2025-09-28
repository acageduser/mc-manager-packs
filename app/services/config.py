import os
import json
import appdirs
from typing import List
from .secret_store import (
    save_pat as _save_pat_dpapi,
    load_pat as _load_pat_dpapi,
    store_path as _secrets_path,
)

APP_NAME = "MinecraftManager"
SETTINGS_DIR = appdirs.user_data_dir(APP_NAME, appauthor=False, roaming=False)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

NEVER_TOUCH = ["saves", "screenshots", "logs", "crash-reports"]

DEFAULT_CHECKED = [
    "config", "journeymap", "libraries", "mods", "resourcepacks", "shaderpacks",
    "options.txt", "optionsof.txt", "optionsshaders.txt", "servers.dat"
]

def default_minecraft_path() -> str:
    appdata = os.environ.get("APPDATA") or ""
    return os.path.join(appdata, ".minecraft") if appdata else ""

def _default_settings() -> dict:
    return {
        "repo_owner": "acageduser",
        "repo_name": "mc-manager-packs",
        "minecraft_path": default_minecraft_path(),
        "dry_run": False,
        "keep_backups": 3,
        "telemetry_enabled": False,
        "last_applied_version": "",
        # UI preference
        "start_tab": "user",      # NEW: "user" or "admin"
        # User automation
        "auto_update": False,
        "auto_close":  False,
        # Admin automation
        "auto_build":  False,
        "auto_publish": False,
        # saved selection for admin tree
        "include_selected": list(DEFAULT_CHECKED),
    }

def _ensure_dir():
    os.makedirs(SETTINGS_DIR, exist_ok=True)

def load_settings() -> dict:
    _ensure_dir()
    if not os.path.exists(SETTINGS_FILE):
        data = _default_settings()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # backfill missing keys
    baseline = _default_settings()
    for k, v in baseline.items():
        data.setdefault(k, v)
    return data

def save_settings(data: dict):
    _ensure_dir()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def settings_store_location() -> str: return SETTINGS_FILE
def pat_store_location() -> str: return _secrets_path()

def set_pat(token: str) -> str: return _save_pat_dpapi(token)
def get_pat() -> str | None: return os.environ.get("GITHUB_TOKEN") or _load_pat_dpapi()

def get_include_selection() -> List[str]:
    return list(load_settings().get("include_selected", DEFAULT_CHECKED))

def set_include_selection(paths: List[str]):
    s = load_settings()
    s["include_selected"] = list(paths)
    save_settings(s)
