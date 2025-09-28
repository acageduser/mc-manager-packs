import os
import sys
import tempfile
import zipfile

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QProgressBar, QLineEdit, QSpinBox, QCheckBox, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QComboBox,
)
from PySide6.QtCore import Qt, QTimer

# No tri-state: only Checked/Unchecked
TRI_STATE = None

from ..services.config import (
    load_settings, save_settings, default_minecraft_path,
    NEVER_TOUCH,
    set_pat, get_include_selection, set_include_selection,
    pat_store_location, settings_store_location,
)
from ..services.github_api import get_latest_manifest, download_asset, sha256_file, publish_pack
from ..services.minecraft import apply_manifest, build_pack, backups_dir
from ..services.threading_worker import run_in_thread

# Palette
PALE_FOREST   = "#8FBC8F"  # user tab "Update"
MUTED_RED     = "#b87979"  # user tab "Cancel"

# Admin muted colors
MUTED_BLUE    = "#6c8ebf"  # Build
MUTED_PURPLE  = "#8a7ea9"  # Publish
MUTED_GREEN   = "#7fb77e"  # Save
MUTED_ORANGE  = "#c9996b"  # Reset (destructive)

def _btn_style(bg_hex: str, fg_hex: str = "white"):
    return (
        f"QPushButton {{ background-color: {bg_hex}; color: {fg_hex}; "
        f"font-weight: 600; height: 34px; border-radius: 6px; }}"
        f"QPushButton:disabled {{ opacity: 0.6; }}"
    )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minecraft Manager")
        self.resize(980, 660)
        self.s = load_settings()

        # workers/threads
        self._worker = None
        self._task = None
        self._build_worker = None
        self._build_thread = None
        self._publish_worker = None
        self._publish_thread = None
        self._last_pack = None  # (zip_path, manifest_path)

        # ---- tiny action queue for startup automation ----
        # actions: "user_update", "admin_build", "admin_publish", "close"
        self._action_queue: list[str] = []
        self._current_action: str | None = None

        tabs = QTabWidget()
        tabs.addTab(self._user_tab(), "User")
        tabs.addTab(self._admin_tab(), "Admin")
        tabs.addTab(self._settings_tab(), "Settings")

        # remember tabs and honor preferred start screen
        self.tabs = tabs
        start = str(self.s.get("start_tab", "user")).lower()
        self.tabs.setCurrentIndex(1 if start == "admin" else 0)

        self.setCentralWidget(tabs)

        # build & run startup queue after UI is ready
        QTimer.singleShot(250, self._schedule_startup_actions)

    # ---------------- Action queue ----------------
    def _schedule_startup_actions(self):
        self._action_queue.clear()

        if bool(self.s.get("auto_update", False)):
            self._action_queue.append("user_update")
        else:
            if bool(self.s.get("auto_build", False)):
                self._action_queue.append("admin_build")
            if bool(self.s.get("auto_publish", False)):
                self._action_queue.append("admin_publish")

        if bool(self.s.get("auto_close", False)) and self._action_queue:
            self._action_queue.append("close")

        if self._action_queue:
            self._run_next_action()

    def _run_next_action(self):
        if not self._action_queue:
            self._current_action = None
            return
        self._current_action = self._action_queue.pop(0)
        act = self._current_action
        if act == "user_update":
            self._user_update_latest()
        elif act == "admin_build":
            self._admin_build_pack()
        elif act == "admin_publish":
            self._admin_publish()
        elif act == "close":
            QTimer.singleShot(400, QApplication.instance().quit)
        else:
            self._run_next_action()

    def _action_done(self, success: bool):
        if not success:
            # stop the chain on failure
            self._action_queue.clear()
            self._current_action = None
            return
        self._run_next_action()

    # ========================= USER =========================
    def _user_tab(self):
        w = QWidget(); v = QVBoxLayout(w)

        top = QHBoxLayout()
        self.btnUpdate = QPushButton("Update to Latest")
        self.btnUpdate.setStyleSheet(
            f"QPushButton {{ background-color: {PALE_FOREST}; color: black; font-weight: 600; height: 36px; }}"
        )
        self.btnCancel = QPushButton("Cancel")
        self.btnCancel.setStyleSheet(
            f"QPushButton {{ background-color: {MUTED_RED}; color: white; height: 36px; }}"
        )
        self.btnCancel.setEnabled(False)
        self.btnUpdate.clicked.connect(self._user_update_latest)
        self.btnCancel.clicked.connect(self._cancel_task)
        top.addWidget(self.btnUpdate, 3); top.addWidget(self.btnCancel, 1)
        v.addLayout(top)

        hl = QHBoxLayout()
        self.lblLocal = QLabel(f"Local: {self.s.get('last_applied_version') or '(unknown)'}")
        self.lblLatest = QLabel("Latest: (unknown)")
        hl.addWidget(self.lblLocal); hl.addStretch(1); hl.addWidget(self.lblLatest)
        v.addLayout(hl)

        self.progress = QProgressBar(); self.progress.setValue(0)
        v.addWidget(self.progress)

        v.addWidget(QLabel("Preview / Log:"))
        self.log = QTextEdit(); self.log.setReadOnly(True)
        v.addWidget(self.log, 1)

        hb = QHBoxLayout()
        btnOpenBackups = QPushButton("Open Backups Folder")
        btnOpenBackups.clicked.connect(lambda: os.startfile(backups_dir()))
        hb.addStretch(1); hb.addWidget(btnOpenBackups)
        v.addLayout(hb)
        return w

    def _append_log(self, msg: str): self.log.append(msg)
    def _cancel_task(self):
        if self._worker: self._worker.cancel()

    def _user_update_latest(self):
        self.log.clear()
        dry = bool(self.s.get("dry_run", False))

        def job(progress=None, log=None, cancelled=None):
            mani = get_latest_manifest(progress, log)
            ver = mani.get("version") or "(missing)"
            log(f"[MANIFEST] version {ver}")
            self.lblLatest.setText(f"Latest: {ver}")

            tmp = tempfile.mkdtemp(prefix="mcman_")
            asset = mani.get("asset", "minecraft-pack.zip")
            log(f"[DOWNLOAD] {asset}")
            zpath = download_asset(asset, tmp, progress, log)

            sha = sha256_file(zpath)
            if sha.lower() != str(mani.get("sha256", "")).lower():
                raise RuntimeError(f"SHA256 mismatch; expected {mani.get('sha256')}, got {sha}")
            log("[SHA256] OK")

            ex = os.path.join(tmp, "extracted")
            with zipfile.ZipFile(zpath) as z:
                z.extractall(ex)

            apply_manifest(ex, mani, dry_run=dry, log=log)
            return mani

        th, worker = run_in_thread(job)
        self._task, self._worker = th, worker
        worker.message.connect(self._append_log)
        worker.progressed.connect(lambda p: self.progress.setValue(int(p*100)))
        worker.failed.connect(lambda e: (self._append_log(f"[ERROR] {e}"), self._action_done(False)))
        worker.started.connect(lambda: self.btnCancel.setEnabled(True))

        def done(mani):
            if mani and not dry:
                self.s = load_settings()
                self.lblLocal.setText(f"Local: {self.s.get('last_applied_version') or '(unknown)'}")
                self._append_log("Update Complete!")
                if bool(self.s.get("auto_close", False)) and not self._action_queue:
                    self._append_log("[Info] Auto Close enabled — exiting…")
                    QTimer.singleShot(1200, QApplication.instance().quit)
                if self._current_action == "user_update":
                    self._action_done(True)
            self.btnCancel.setEnabled(False)
            self.progress.setValue(0)

        worker.finished.connect(done)
        th.finished.connect(lambda: th.deleteLater())
        th.start()

    # ========================= ADMIN =========================
    def _admin_tab(self):
        w = QWidget(); v = QVBoxLayout(w)

        # Tree (always enabled; no lock)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Include in pack"])
        self.tree.itemClicked.connect(self._toggle_row_check)
        self.tree.itemChanged.connect(self._on_tree_item_changed)
        v.addWidget(self.tree, 1)
        self._populate_tree()

        # Buttons (order: Build, Publish, Save, Reset)
        row2 = QHBoxLayout()

        self.btnBuild   = QPushButton("Build Pack")
        self.btnPublish = QPushButton("Publish to GitHub Release")
        self.btnSaveSel = QPushButton("Save Selection")
        self.btnResetSel= QPushButton("Reset Pack")

        # Styles
        self.btnBuild.setStyleSheet(_btn_style(MUTED_BLUE))
        self.btnPublish.setStyleSheet(_btn_style(MUTED_PURPLE))
        self.btnSaveSel.setStyleSheet(_btn_style(MUTED_GREEN))
        self.btnResetSel.setStyleSheet(_btn_style(MUTED_ORANGE))

        # Wiring
        self.btnBuild.clicked.connect(self._admin_build_pack)
        self.btnPublish.clicked.connect(self._admin_publish)
        self.btnSaveSel.clicked.connect(self._admin_save_selection)
        self.btnResetSel.clicked.connect(self._admin_reset_selection)

        # Add in requested order
        row2.addWidget(self.btnBuild)
        row2.addWidget(self.btnPublish)
        row2.addWidget(self.btnSaveSel)
        row2.addWidget(self.btnResetSel)
        v.addLayout(row2)

        # Shared progress bar
        self.adminProgress = QProgressBar(); self.adminProgress.setValue(0)
        v.addWidget(self.adminProgress)

        self.adminLog = QTextEdit(); self.adminLog.setReadOnly(True)
        v.addWidget(self.adminLog, 1)

        return w

    # ----- Tree helpers -----
    def _populate_tree(self):
        self.tree.clear()
        root_path = self.s.get("minecraft_path") or default_minecraft_path()
        selected = set(get_include_selection())

        def add_dir(parent_item, dir_path, rel_root=""):
            try:
                entries = sorted(os.listdir(dir_path))
            except FileNotFoundError:
                return
            for name in entries:
                full = os.path.join(dir_path, name)
                rel = os.path.normpath(os.path.join(rel_root, name)).replace("\\", "/")

                item = QTreeWidgetItem([rel])
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)

                top_part = rel.split("/")[0]
                if top_part in NEVER_TOUCH:
                    item.setCheckState(0, Qt.Unchecked)
                    item.setDisabled(True)
                elif rel in selected or top_part in selected:
                    item.setCheckState(0, Qt.Checked)
                else:
                    item.setCheckState(0, Qt.Unchecked)

                parent_item.addChild(item)
                if os.path.isdir(full):
                    add_dir(item, full, rel)

        top = QTreeWidgetItem([root_path])
        top.setFlags(top.flags() & ~Qt.ItemIsUserCheckable)  # visual root label
        self.tree.addTopLevelItem(top)
        top.setExpanded(True)
        add_dir(top, root_path, "")

    def _toggle_row_check(self, item: QTreeWidgetItem, column: int):
        if not (item.flags() & Qt.ItemIsUserCheckable):
            return
        new_state = Qt.Unchecked if item.checkState(0) == Qt.Checked else Qt.Checked
        item.setCheckState(0, new_state)  # triggers _on_tree_item_changed

    def _set_subtree(self, item: QTreeWidgetItem, state):
        for i in range(item.childCount()):
            ch = item.child(i)
            if ch.isDisabled():
                self._set_subtree(ch, state)
                continue
            if ch.flags() & Qt.ItemIsUserCheckable:
                ch.setCheckState(0, state)
            self._set_subtree(ch, state)

    def _recompute_parent_chain(self, item: QTreeWidgetItem):
        parent = item.parent()
        while parent:
            if parent.flags() & Qt.ItemIsUserCheckable:
                total = 0; checked = 0
                for i in range(parent.childCount()):
                    ch = parent.child(i)
                    if ch.isDisabled():
                        continue
                    total += 1
                    if ch.checkState(0) == Qt.Checked:
                        checked += 1
                parent.setCheckState(0, Qt.Checked if total and checked == total else Qt.Unchecked)
            parent = parent.parent()

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        if column != 0:
            return
        state = item.checkState(0)
        self.tree.blockSignals(True)
        self._set_subtree(item, state)
        self.tree.blockSignals(False)
        self._recompute_parent_chain(item)

    def _selected_paths(self):
        out = set()
        def walk(node: QTreeWidgetItem, parent_included: bool = False):
            for i in range(node.childCount()):
                ch = node.child(i)
                if ch.isDisabled():
                    walk(ch, parent_included); continue
                rel = ch.text(0)
                checked = (ch.checkState(0) == Qt.Checked)
                if checked and not parent_included:
                    out.add(rel); walk(ch, True)
                else:
                    walk(ch, parent_included or checked)
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return sorted(out)

    def _out_dir(self) -> str:
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        out_dir = os.path.join(base, "out")
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    # ----- Admin actions -----
    def _admin_save_selection(self):
        sel = self._selected_paths()
        set_include_selection(sel)
        self.adminLog.append(f"[SAVED] {len(sel)} paths.")
        self.adminLog.append(f"[SAVED AT] {settings_store_location()}")

    def _admin_reset_selection(self):
        reply = QMessageBox.question(
            self, "Confirm Reset", "Are you sure you want to reset the Pack?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.adminLog.append("[CANCELLED] Reset Pack."); return

        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            self._set_subtree(top, Qt.Unchecked)
            if top.flags() & Qt.ItemIsUserCheckable:
                top.setCheckState(0, Qt.Unchecked)
        self.tree.blockSignals(False)
        self.adminLog.append("[OK] Selection reset (all unchecked).")

    def _admin_build_pack(self):
        include = self._selected_paths()
        if not include:
            self.adminLog.append("[WARN] Nothing selected."); return

        out_dir = self._out_dir()

        # Print absolute minecraft path & out dir
        mc_root = (load_settings().get("minecraft_path") or "").strip()
        self.adminLog.append(f"[UI] MC ROOT: {mc_root}")
        self.adminLog.append(f"[UI] OUT DIR: {out_dir}")
        self.adminLog.append(f"[UI] Starting build; {len(include)} selection(s)")
        for rel in include:
            self.adminLog.append(f"[UI] include: {rel}")

        # Disable while building; show busy
        self.btnBuild.setEnabled(False)
        self.btnPublish.setEnabled(False)
        self.btnResetSel.setEnabled(False)
        self.adminProgress.setRange(0, 0)

        def job(progress=None, log=None, cancelled=None):
            log(f"[START] Building pack to: {out_dir}")
            log(f"[INFO] Items selected: {len(include)}")
            if progress: progress(0.05)
            z, mani, meta = build_pack(include, out_dir, log, progress)
            self._last_pack = (z, mani)
            if progress: progress(0.98)
            log(f"[DONE] Pack: {z}")
            log(f"[DONE] Manifest: {mani} (sha256 {meta['sha256']})")
            if progress: progress(1.0)
            return True

        th, worker = run_in_thread(job)
        self._build_thread, self._build_worker = th, worker

        worker.message.connect(lambda s: self.adminLog.append(s))
        worker.progressed.connect(self._admin_progress)
        worker.failed.connect(lambda e: self._admin_build_cleanup(error=str(e)))
        worker.finished.connect(lambda *_: self._admin_build_cleanup())
        th.finished.connect(lambda: (self._admin_build_cleanup(), th.deleteLater()))
        th.start()

    def _admin_progress(self, p: float):
        if self.adminProgress.maximum() == 0:  # switch from busy to determinate
            self.adminProgress.setRange(0, 100)
        self.adminProgress.setValue(int(p * 100))

    def _admin_build_cleanup(self, error: str | None = None):
        if error:
            self.adminLog.append(f"[ERROR] {error}")
        self.btnBuild.setEnabled(True)
        self.btnPublish.setEnabled(True)
        self.btnResetSel.setEnabled(True)
        self.adminProgress.setRange(0, 100)
        self.adminProgress.setValue(0)
        self._build_thread = None
        self._build_worker = None

        # queue chaining: if we were in "admin_build", continue (or stop on error)
        if self._current_action == "admin_build":
            self._action_done(success=(error is None))

    def _admin_publish(self):
        z_m = self._last_pack
        if not z_m:
            z = os.path.join(self._out_dir(), "minecraft-pack.zip")
            m = os.path.join(self._out_dir(), "manifest.json")
            if not (os.path.exists(z) and os.path.exists(m)):
                self.adminLog.append("[ERROR] Build a pack first (no out\\ files found)."); return
            z_m = (z, m)

        zip_path, manifest_path = z_m

        # Disable a few controls and prepare a determinate bar for upload progress
        self.btnPublish.setEnabled(False)
        self.btnBuild.setEnabled(False)
        self.btnResetSel.setEnabled(False)
        self.adminProgress.setRange(0, 100)
        self.adminProgress.setValue(0)

        def job(progress=None, log=None, cancelled=None):
            log("[START] Publishing release...")
            tag = publish_pack(manifest_path, zip_path, log=log, progress=progress)
            log(f"[DONE] Release tag: {tag}")
            return tag

        th, worker = run_in_thread(job)
        self._publish_thread, self._publish_worker = th, worker

        worker.message.connect(lambda s: self.adminLog.append(s))
        worker.progressed.connect(self._admin_progress)  # live progress
        worker.failed.connect(lambda e: self._admin_publish_cleanup(error=str(e)))
        worker.finished.connect(lambda *_: self._admin_publish_cleanup())
        th.finished.connect(lambda: th.deleteLater())
        th.start()

    def _admin_publish_cleanup(self, error: str | None = None):
        if error:
            self.adminLog.append(f"[ERROR] {error}")
        else:
            self.adminLog.append("[DONE] Publish Complete.")
        self.btnPublish.setEnabled(True)
        self.btnBuild.setEnabled(True)
        self.btnResetSel.setEnabled(True)
        self.adminProgress.setValue(0)
        self._publish_thread = None
        self._publish_worker = None

        # queue chaining: if we were in "admin_publish", continue (or stop on error)
        if self._current_action == "admin_publish":
            self._action_done(success=(error is None))

    # ======================== SETTINGS ========================
    def _settings_tab(self):
        w = QWidget(); v = QVBoxLayout(w)

        v.addWidget(QLabel("Owner / Org:"));  self.edOwner = QLineEdit(self.s.get("repo_owner","")); v.addWidget(self.edOwner)
        v.addWidget(QLabel("Repository:"));   self.edRepo  = QLineEdit(self.s.get("repo_name",""));  v.addWidget(self.edRepo)

        v.addWidget(QLabel("Minecraft Path:"))
        row2 = QHBoxLayout()
        self.edPath = QLineEdit(self.s.get("minecraft_path") or default_minecraft_path())
        btnFind = QPushButton("Find .minecraft"); btnFind.clicked.connect(self._settings_find_mc)
        row2.addWidget(self.edPath); row2.addWidget(btnFind)
        v.addLayout(row2)

        # NEW: Start screen preference
        rowStart = QHBoxLayout()
        rowStart.addWidget(QLabel("Start screen:"))
        self.startTab = QComboBox()
        self.startTab.addItems(["User", "Admin"])
        current = "Admin" if str(self.s.get("start_tab", "user")).lower() == "admin" else "User"
        self.startTab.setCurrentText(current)
        rowStart.addWidget(self.startTab); rowStart.addStretch(1)
        v.addLayout(rowStart)


        self.cbDry = QCheckBox("Dry run (preview actions)")
        self.cbDry.setChecked(bool(self.s.get("dry_run", False)))
        v.addWidget(self.cbDry)

        # Automatic Update Mode (User)
        self.cbAuto = QCheckBox("Automatic Update Mode (run update on startup)")
        self.cbAuto.setChecked(bool(self.s.get("auto_update", False)))
        v.addWidget(self.cbAuto)

        # Auto Close after successful update / admin queue
        self.cbAutoClose = QCheckBox("Auto Close after successful task (User/Admin)")
        self.cbAutoClose.setChecked(bool(self.s.get("auto_close", False)))
        v.addWidget(self.cbAutoClose)

        # --- Admin automation toggles ---
        self.cbAutoBuild   = QCheckBox("Auto Build Pack on startup (admin)")
        self.cbAutoPublish = QCheckBox("Auto Publish to GitHub Release on startup (admin)")
        self.cbAutoBuild.setChecked(bool(self.s.get("auto_build", False)))
        self.cbAutoPublish.setChecked(bool(self.s.get("auto_publish", False)))
        v.addWidget(self.cbAutoBuild)
        v.addWidget(self.cbAutoPublish)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Keep backups (count):"))
        self.keepSpin = QSpinBox(); self.keepSpin.setRange(1,50); self.keepSpin.setValue(int(self.s.get("keep_backups",3)))
        self.keepSpin.setFixedHeight(28); self.keepSpin.setMinimumWidth(90)
        row3.addWidget(self.keepSpin); row3.addStretch(1)
        v.addLayout(row3)

        self.edPAT = QLineEdit(); self.edPAT.setPlaceholderText("GitHub PAT"); self.edPAT.setEchoMode(QLineEdit.Password)
        btnPAT = QPushButton("Save PAT (DPAPI)")
        btnPAT.clicked.connect(self._save_pat_clicked)
        row4 = QHBoxLayout(); row4.addWidget(self.edPAT); row4.addWidget(btnPAT); v.addLayout(row4)

        btnSave = QPushButton("Save Settings"); btnSave.clicked.connect(self._settings_save); v.addWidget(btnSave)
        self.status = QLabel(""); v.addWidget(self.status)
        return w

    def _settings_find_mc(self):
        p = default_minecraft_path()
        self.edPath.setText(p); self._flash_status(f"Detected: {p}")

    def _save_pat_clicked(self):
        token = self.edPAT.text().strip()
        if not token:
            self._flash_status("Enter a PAT first.")
            return
        try:
            saved_at = set_pat(token)  # returns the path
            self.edPAT.setText("")
            self._flash_status(f"PAT saved locally at: {saved_at}")
        except Exception as e:
            self._flash_status(f"[ERROR] {e}")

    def _flash_status(self, msg): self.status.setText(msg)

    def _settings_save(self):
        self.s["repo_owner"]     = self.edOwner.text().strip()
        self.s["repo_name"]      = self.edRepo.text().strip()
        self.s["minecraft_path"] = self.edPath.text().strip()
        self.s["dry_run"]        = self.cbDry.isChecked()
        # User automation
        self.s["auto_update"]    = self.cbAuto.isChecked()
        self.s["auto_close"]     = self.cbAutoClose.isChecked()
        # Admin automation
        self.s["auto_build"]     = self.cbAutoBuild.isChecked()
        self.s["auto_publish"]   = self.cbAutoPublish.isChecked()
        self.s["keep_backups"]   = int(self.keepSpin.value())

        # NEW: start tab
        self.s["start_tab"] = "admin" if self.startTab.currentText().lower() == "admin" else "user"

        save_settings(self.s)
        self._flash_status(f"Saved settings to: {settings_store_location()}")

        # reflect immediately
        if hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(1 if self.s["start_tab"] == "admin" else 0)
