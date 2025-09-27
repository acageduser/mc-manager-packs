import base64
try:
    import win32crypt  # type: ignore
except Exception:
    win32crypt = None

def protect_string(plain: str) -> str:
    """Protect a string with Windows DPAPI and return base64."""
    if not plain:
        return ""
    if win32crypt is None:
        # Dev fallback (not secure): base64 the plain text
        return base64.b64encode(plain.encode("utf-8")).decode("ascii")
    blob = win32crypt.CryptProtectData(plain.encode("utf-8"), None, None, None, 0)
    # pywin32 may return bytes or (desc, bytes); normalize
    if isinstance(blob, (tuple, list)):
        blob = blob[1]
    return base64.b64encode(blob).decode("ascii")

def unprotect_string(protected_b64: str) -> str:
    """Unprotect a base64 string created by protect_string."""
    if not protected_b64:
        return ""
    raw = base64.b64decode(protected_b64.encode("ascii"))
    if win32crypt is None:
        # Dev fallback
        return raw.decode("utf-8", errors="ignore")
    out = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
    if isinstance(out, (tuple, list)):
        out = out[1]
    return out.decode("utf-8")
