"""Trwałe zgłoszenia terenowe i odrębna baza podglądu importów (SQLite)."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4

STATE_PATH = Path(os.getenv("AED_STATE_PATH", str(Path(__file__).parent / "data/state/aed.sqlite3")))


class FeatureStore:
    def __init__(self, path=STATE_PATH):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY, aed_id TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS reports_aed ON reports(aed_id,created_at);
          CREATE TABLE IF NOT EXISTS imports (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0);
        """)

    def close(self):
        with self.lock:
            self.db.close()

    def report(self, aed_id, kind, now):
        item = {"id": uuid4().hex, "aed_id": aed_id, "kind": kind, "created_at": now.astimezone(timezone.utc).isoformat()}
        with self.lock, self.db:
            self.db.execute("INSERT INTO reports VALUES(:id,:aed_id,:kind,:created_at)", item)
        return item

    def overlay(self, records, now):
        with self.lock:
            reports = [dict(r) for r in self.db.execute("SELECT * FROM reports ORDER BY created_at DESC,id DESC")]
        return overlay_reports(records, reports, now)

    def save_import(self, payload, now):
        identifier = uuid4().hex
        with self.lock, self.db:
            self.db.execute("INSERT INTO imports VALUES(?,?,?,0)", (identifier, now.isoformat(), json.dumps(payload, ensure_ascii=False, allow_nan=False)))
        return identifier

    def activate_import(self, identifier):
        with self.lock, self.db:
            row = self.db.execute("SELECT payload FROM imports WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            self.db.execute("UPDATE imports SET active=1 WHERE id=?", (identifier,))
        return json.loads(row["payload"])

    def preview(self):
        with self.lock:
            rows = self.db.execute("SELECT id,payload FROM imports WHERE active=1 ORDER BY created_at DESC LIMIT 20").fetchall()
        return [{**r, "is_preview": True, "import_id": batch["id"]} for batch in rows
                for r in json.loads(batch["payload"]).get("normalized_json", [])]


def overlay_reports(records, reports, now):
    latest, adverse, counts = {}, {}, {}
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=24)
    for r in reports:
        aid = r["aed_id"]
        latest.setdefault(aid, r)
        counts[aid] = counts.get(aid, 0) + 1
        if r["kind"] in ("closed", "damaged") and datetime.fromisoformat(r["created_at"]) >= cutoff:
            adverse.setdefault(aid, r)
    output = []
    for row in records:
        ids = [row["id_aed"], *row.get("merged_ids", [])]
        matches = [latest[i] for i in ids if i in latest]
        if not matches:
            output.append(row); continue
        last = max(matches, key=lambda r: r["created_at"])
        alerts = [adverse[i] for i in ids if i in adverse]
        # Pozytywne anonimowe zgłoszenie nie kasuje świeżego ostrzeżenia o uszkodzeniu.
        alert = max(alerts, key=lambda r: (r["kind"] == "damaged", r["created_at"])) if alerts else None
        output.append({**row, "last_field_verification": last["created_at"], "field_report": last,
                       "field_reports_count": sum(counts.get(i, 0) for i in set(ids)),
                       "field_access_alert": alert["kind"] if alert else None,
                       "field_alert_until": (datetime.fromisoformat(alert["created_at"]) + timedelta(hours=24)).isoformat() if alert else None,
                       "confidence_score": round(max(0, min(100, row.get("confidence_score", 0) + (-10 if alert else 5 if last["kind"]=="working" else -5))), 1)})
    return output

