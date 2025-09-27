import os
import json
import appdirs
from typing import List

# DPAPI-backed secret store (same base dir as settings.json)
from .secret_store import (
    save_pat as _save_pat_dpapi,
    load_pat as _load_pat_dpapi,
    store_path as _secrets_path,
)

APP_NAME = "MinecraftManager"
# %LOCALAPPDATA%\MinecraftManager
SETTINGS_DIR = appdirs.user_data_dir(APP_NAME, appauthor=False, roaming=False)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

# Protected paths never touched
NEVER_TOUCH = ["saves", "screenshots", "logs", "crash-reports"]

# Default checked items for pack build
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
        "auto_update": False,  # NEW: automatically update on app start when enabled
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

    # backfill missing keys but do not remove unknown/legacy keys
    baseline = _default_settings()
    for k, v in baseline.items():
        data.setdefault(k, v)
    return data


def save_settings(data: dict):
    _ensure_dir()
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ----- Locations (for UI diagnostics) -----
def settings_store_location() -> str:
    """Absolute path to settings.json."""
    return SETTINGS_FILE


def pat_store_location() -> str:
    """Absolute path to the encrypted secrets file."""
    return _secrets_path()


# ----- PAT helpers (env takes precedence, else DPAPI) -----
def set_pat(token: str) -> str:
    """
    Save the GitHub PAT securely (DPAPI → %LOCALAPPDATA%\\MinecraftManager\\secrets.json).
    Returns the absolute path to the saved file so the UI can display it.
    """
    return _save_pat_dpapi(token)


def get_pat() -> str | None:
    """
    Return a token for GitHub API calls. Prefer the environment variable if set,
    otherwise decrypt from the DPAPI store.
    """
    return os.environ.get("GITHUB_TOKEN") or _load_pat_dpapi()


# ----- Include selection persistence -----
def get_include_selection() -> List[str]:
    return list(load_settings().get("include_selected", DEFAULT_CHECKED))


def set_include_selection(paths: List[str]):
    s = load_settings()
    s["include_selected"] = list(paths)
    save_settings(s)
