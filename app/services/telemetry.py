from __future__ import annotations
from pathlib import Path
import json, datetime
from .config import settings, settings_dir
from .github_api import create_issue

class Telemetry:
    def __init__(self):
        self.store = Path(settings_dir()) / "telemetry" / "events.json"
        self.store.parent.mkdir(parents=True, exist_ok=True)
        if not self.store.exists():
            self.store.write_text("{}", encoding="utf-8")

    def track(self, name: str):
        if not settings.telemetry_enabled: return
        data = json.loads(self.store.read_text(encoding="utf-8"))
        data[name] = int(data.get(name, 0)) + 1
        self.store.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def flush(self) -> bool:
        if not settings.telemetry_enabled: return False
        data = json.loads(self.store.read_text(encoding="utf-8"))
        if not data: return True
        lines = ["### Telemetry snapshot", "", f"Client: `{settings.telemetry_client_id}`", f"Version: `{settings.last_applied_version or '(unknown)'}`", "", "| event | count |", "|---|---:|"]
        for k,v in data.items():
            lines.append(f"| {k} | {v} |")
        title = f"Telemetry {datetime.datetime.utcnow():%Y-%m-%d %H:%M} UTC • {settings.telemetry_client_id}"
        create_issue(title, "\n".join(lines))
        archive = self.store.with_name(f"events-{datetime.datetime.utcnow():%Y%m%d_%H%M%S}.json")
        archive.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.store.write_text("{}", encoding="utf-8")
        return True
