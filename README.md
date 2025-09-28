# Minecraft Manager (Python / PySide6)

Full GUI app for managing and updating a shared `.minecraft` setup. Useful for Minecraft server admins that want to easily pick exactly what files/folders/settings their players should have. ```SHA256``` protected downloads hosted on GitHub.

## Why I made this

There are a few decent 'auto updater' programs out there however they do not use very good security/safety features. I want to give my users and admins the chance to experience safe and easy server management.
Users can set this up with 'Startup Apps' on a Windows machine to automatically grab any updates.
Admins can take advantage of a full GUI ```.minecraft``` user folder managemnet.

Single source of truth: **GitHub Releases**. Admin features (build & publish) are
available locally; publishing requires a PAT stored securely via **Windows DPAPI**.

---

## Features

- **User tab:** fetch latest release, verify `sha256`, extract, back up, and apply.
- **Admin tab:** choose folders/files to include, build `minecraft-pack.zip` + `manifest.json`, and publish a GitHub Release (with live progress).
- **Settings tab:** configure repo + paths and securely save a GitHub PAT (DPAPI).
- Protected paths that are never touched when applying packs: `saves/`, `screenshots/`, `logs/`, `crash-reports/`.

---

---
## Tabs:
#### User:
<img width="982" height="692" alt="image" src="https://github.com/user-attachments/assets/db71c61b-8c05-4873-83f3-c4da0cf7729b" />

#### Admin:
<img width="982" height="692" alt="image" src="https://github.com/user-attachments/assets/fa3691fe-3c9d-45e7-a617-08e30ff4c69e" />

#### Settings:
<img width="982" height="692" alt="image" src="https://github.com/user-attachments/assets/cf87ecc1-31b3-40ef-ac8a-71bf967925af" />

---

## File tree (reference)

```
.
├─ app/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ ui/
│  │  ├─ __init__.py
│  │  └─ main_window.py
│  └─ services/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ secret_store.py
│     ├─ github_api.py
│     ├─ minecraft.py
│     └─ threading_worker.py
├─ build.bat
├─ requirements.txt
└─ README.md
```

> Note: When running from source, build artifacts may be written to an `out/` folder at the repo root (ignored by `.gitignore`). When running as an EXE, the folder is created next to the executable.

---

## Quick start (dev)

```powershell
# From repo root
py -3.12 -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app\main.py
```

### Build EXE (preferred: batch script)

Double‑click **`build.bat`** (or run from a terminal):

```bat
build.bat
```

Output will appear in `dist\`.

> PowerShell alternative (`build.ps1`) is included but optional.

---

## Configure

First run creates `%LOCALAPPDATA%\MinecraftManager\settings.json`. Set:
- `repo_owner`, `repo_name`
- Optional: in **Settings** → paste a PAT and click **Save PAT (DPAPI)**

**Where is the PAT stored?**  
`%LOCALAPPDATA%\MinecraftManager\secrets.json` (encrypted with Windows **DPAPI**, current user scope). It is **not** saved in `settings.json`, committed to the repo, or embedded in the EXE.

---

## Admin workflow

1. Go to **Admin** tab.
2. Check the folders/files you want included (top‑level protected items are disabled).
3. Click **Build Pack** — this creates `out\minecraft-pack.zip` and `out\manifest.json`.
4. Click **Publish to GitHub Release** — the app creates/uses a release tag based on the manifest version and uploads assets with a live progress bar.

---

## User workflow

1. On the **User** tab, click **Update to Latest**.
2. The app downloads the latest release assets, verifies `sha256`, backs up changed files, and applies the pack to your `.minecraft` (respecting protected paths).

---

## Security

- **PAT**: stored only in `%LOCALAPPDATA%\MinecraftManager\secrets.json` (DPAPI). Never written to the repo.
- **Integrity**: `sha256` of the pack is verified before applying.
- **No secrets in code**: build scripts and app code do not bake or print tokens.

---

## Troubleshooting

- **PyInstaller says a module is missing**: ensure package markers exist (`app/__init__.py`, `app/ui/__init__.py`, `app/services/__init__.py`). The provided `build.bat` creates them if missing.
- **`win32crypt` not available**: install `pywin32` (included via `requirements.txt`). PAT saving requires Windows DPAPI.
- **Publish 400 on upload**: ensure the release exists and that you’re uploading to the returned `upload_url`; the app handles conflicts by deleting/re‑uploading if needed.

---

## License

MIT
