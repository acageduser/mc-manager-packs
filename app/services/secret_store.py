#app\services\secret_store.py

import os
import json
import base64
from appdirs import user_data_dir

try:
    import win32crypt  # from pywin32
except Exception:
    win32crypt = None

# Keep this app name identical to config.py so paths match.
_APP_NAME = "MinecraftManager"

def _dir() -> str:
    """
    Store secrets alongside settings.json:
    %LOCALAPPDATA%\\MinecraftManager
    (no author subfolder, non-roaming)
    """
    d = user_data_dir(_APP_NAME, appauthor=False, roaming=False)
    os.makedirs(d, exist_ok=True)
    return d

def _path() -> str:
    return os.path.join(_dir(), "secrets.json")

def save_pat(token: str) -> str:
    """
    Encrypt and save the PAT using Windows DPAPI (current user context).
    Returns the absolute file path where it was stored.
    """
    if not token:
        raise ValueError("Empty PAT")
    if not win32crypt:
        raise RuntimeError("Windows DPAPI (pywin32) is not available on this system.")

    # CryptProtectData returns an opaque encrypted bytes blob.
    blob = win32crypt.CryptProtectData(
        token.encode("utf-8"),
        "gh_pat",              # optional description
        None, None, None, 0
    )
    data = {"pat_dpapi": base64.b64encode(blob).decode("ascii")}
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return _path()

def load_pat() -> str | None:
    """
    Read and decrypt the PAT from the secure store. Returns None if missing/unavailable.
    """
    p = _path()
    if not os.path.exists(p) or not win32crypt:
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        b64 = data.get("pat_dpapi")
        if not b64:
            return None
        blob = base64.b64decode(b64)
        # CryptUnprotectData returns (description, decrypted_bytes)
        decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1]
        return decrypted.decode("utf-8")
    except Exception:
        return None

def store_path() -> str:
    """Return the absolute path to secrets.json (for diagnostics/UI)."""
    return _path()
