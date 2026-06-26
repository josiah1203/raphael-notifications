"""Notifications store — in-app inbox + preferences."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class NotificationsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        path = db_path or Path(os.environ.get("RAPHAEL_NOTIFICATIONS_DB", "/tmp/raphael-notifications.db"))
        self.db_path = path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT,
                    read INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    data TEXT
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    user_id TEXT PRIMARY KEY,
                    email_digest INTEGER DEFAULT 1,
                    review_alerts INTEGER DEFAULT 1,
                    mention_alerts INTEGER DEFAULT 1,
                    invite_alerts INTEGER DEFAULT 1
                );
                """
            )

    def add(self, user_id: str, ntype: str, title: str, body: str = "", data: dict | None = None) -> dict[str, Any]:
        nid = f"ntf_{int(datetime.now(timezone.utc).timestamp())}"
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO notifications (id, user_id, type, title, body, created_at, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nid, user_id, ntype, title, body, now, json.dumps(data or {})),
            )
        return {"id": nid, "user_id": user_id, "type": ntype, "title": title, "read": False, "created_at": now}

    def list_for_user(self, user_id: str, unread_only: bool = False) -> list[dict[str, Any]]:
        with self._conn() as conn:
            q = "SELECT id, type, title, body, read, created_at FROM notifications WHERE user_id = ?"
            if unread_only:
                q += " AND read = 0"
            q += " ORDER BY created_at DESC LIMIT 100"
            rows = conn.execute(q, (user_id,)).fetchall()
        return [
            {"id": r[0], "type": r[1], "title": r[2], "body": r[3], "read": bool(r[4]), "created_at": r[5]}
            for r in rows
        ]

    def get_prefs(self, user_id: str) -> dict[str, bool]:
        with self._conn() as conn:
            row = conn.execute("SELECT email_digest, review_alerts, mention_alerts, invite_alerts FROM preferences WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return {"emailDigest": True, "reviewAlerts": True, "mentionAlerts": True, "inviteAlerts": True}
        return {"emailDigest": bool(row[0]), "reviewAlerts": bool(row[1]), "mentionAlerts": bool(row[2]), "inviteAlerts": bool(row[3])}

    def set_pref(self, user_id: str, key: str, value: bool) -> dict[str, bool]:
        col_map = {"emailDigest": "email_digest", "reviewAlerts": "review_alerts", "mentionAlerts": "mention_alerts", "inviteAlerts": "invite_alerts"}
        col = col_map.get(key)
        if not col:
            return self.get_prefs(user_id)
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO preferences (user_id, {col}) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET {col} = excluded.{col}",
                (user_id, 1 if value else 0),
            )
        return self.get_prefs(user_id)
