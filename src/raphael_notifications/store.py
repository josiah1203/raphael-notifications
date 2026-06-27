"""Notifications store — Postgres dual-path with SQLite test fallback."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class NotificationsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        from raphael_contracts import db as rdb

        self._postgres = rdb.is_postgres()
        if self._postgres:
            rdb.ensure_migrations()
            self.db_path = Path("postgres")
        else:
            path = db_path or Path(os.environ.get("RAPHAEL_NOTIFICATIONS_DB", "/tmp/raphael-notifications.db"))
            self.db_path = path
            self._init_sqlite()

    def _connect_sqlite(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def _init_sqlite(self) -> None:
        with self._connect_sqlite() as conn:
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
                    invite_alerts INTEGER DEFAULT 1,
                    sms_alerts INTEGER DEFAULT 0,
                    sms_review_alerts INTEGER DEFAULT 0,
                    sms_automation_failures INTEGER DEFAULT 0
                );
                """
            )
            cols = {row[1] for row in conn.execute("PRAGMA table_info(preferences)").fetchall()}
            for col, default in [
                ("sms_alerts", 0),
                ("sms_review_alerts", 0),
                ("sms_automation_failures", 0),
            ]:
                if col not in cols:
                    conn.execute(f"ALTER TABLE preferences ADD COLUMN {col} INTEGER DEFAULT {default}")

    def _prefs_table(self) -> str:
        return "notification_preferences" if self._postgres else "preferences"

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if self._postgres:
            from raphael_contracts.db import pg_execute

            pg_execute(sql, params)
            return
        with self._connect_sqlite() as conn:
            conn.execute(sql, params)
            conn.commit()

    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> Any | None:
        if self._postgres:
            from raphael_contracts.db import pg_fetchone

            return pg_fetchone(sql, params)
        with self._connect_sqlite() as conn:
            return conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
        if self._postgres:
            from raphael_contracts.db import pg_fetchall

            return pg_fetchall(sql, params)
        with self._connect_sqlite() as conn:
            return conn.execute(sql, params).fetchall()

    def add(self, user_id: str, ntype: str, title: str, body: str = "", data: dict | None = None) -> dict[str, Any]:
        nid = f"ntf_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(data or {})
        if self._postgres:
            self._execute(
                """
                INSERT INTO notifications (id, user_id, type, title, body, created_at, data)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (nid, user_id, ntype, title, body, now, payload),
            )
        else:
            self._execute(
                "INSERT INTO notifications (id, user_id, type, title, body, created_at, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nid, user_id, ntype, title, body, now, payload),
            )
        return {"id": nid, "user_id": user_id, "type": ntype, "title": title, "read": False, "created_at": now}

    def list_for_user(self, user_id: str, unread_only: bool = False) -> list[dict[str, Any]]:
        if self._postgres:
            q = (
                "SELECT id, type, title, body, read, created_at FROM notifications WHERE user_id = %s"
                + (" AND read = FALSE" if unread_only else "")
                + " ORDER BY created_at DESC LIMIT 100"
            )
        else:
            q = "SELECT id, type, title, body, read, created_at FROM notifications WHERE user_id = ?"
            if unread_only:
                q += " AND read = 0"
            q += " ORDER BY created_at DESC LIMIT 100"
        rows = self._fetchall(q, (user_id,))
        return [
            {
                "id": row["id"] if isinstance(row, dict) else row[0],
                "type": row["type"] if isinstance(row, dict) else row[1],
                "title": row["title"] if isinstance(row, dict) else row[2],
                "body": row["body"] if isinstance(row, dict) else row[3],
                "read": bool(row["read"] if isinstance(row, dict) else row[4]),
                "created_at": str(row["created_at"] if isinstance(row, dict) else row[5]),
            }
            for row in rows
        ]

    def mark_read(self, user_id: str, notification_id: str) -> dict[str, Any] | None:
        if self._postgres:
            from raphael_contracts.db import pg_execute

            cur = pg_execute(
                "UPDATE notifications SET read = TRUE WHERE id = %s AND user_id = %s",
                (notification_id, user_id),
            )
            if cur.rowcount == 0:
                return None
        else:
            with self._connect_sqlite() as conn:
                cur = conn.execute(
                    "UPDATE notifications SET read = 1 WHERE id = ? AND user_id = ?",
                    (notification_id, user_id),
                )
                if cur.rowcount == 0:
                    return None
                conn.commit()
        return {"id": notification_id, "read": True}

    def get_prefs(self, user_id: str) -> dict[str, bool]:
        table = self._prefs_table()
        row = self._fetchone(
            f"SELECT email_digest, review_alerts, mention_alerts, invite_alerts, "
            f"sms_alerts, sms_review_alerts, sms_automation_failures "
            f"FROM {table} WHERE user_id = {'%s' if self._postgres else '?'}",
            (user_id,),
        )
        if not row:
            return {
                "emailDigest": True,
                "reviewAlerts": True,
                "mentionAlerts": True,
                "inviteAlerts": True,
                "smsAlerts": False,
                "smsReviewAlerts": False,
                "smsAutomationFailures": False,
            }
        return {
            "emailDigest": bool(row["email_digest"] if isinstance(row, dict) else row[0]),
            "reviewAlerts": bool(row["review_alerts"] if isinstance(row, dict) else row[1]),
            "mentionAlerts": bool(row["mention_alerts"] if isinstance(row, dict) else row[2]),
            "inviteAlerts": bool(row["invite_alerts"] if isinstance(row, dict) else row[3]),
            "smsAlerts": bool(row["sms_alerts"] if isinstance(row, dict) else row[4]),
            "smsReviewAlerts": bool(row["sms_review_alerts"] if isinstance(row, dict) else row[5]),
            "smsAutomationFailures": bool(row["sms_automation_failures"] if isinstance(row, dict) else row[6]),
        }

    def set_pref(self, user_id: str, key: str, value: bool) -> dict[str, bool]:
        col_map = {
            "emailDigest": "email_digest",
            "reviewAlerts": "review_alerts",
            "mentionAlerts": "mention_alerts",
            "inviteAlerts": "invite_alerts",
            "smsAlerts": "sms_alerts",
            "smsReviewAlerts": "sms_review_alerts",
            "smsAutomationFailures": "sms_automation_failures",
        }
        col = col_map.get(key)
        if not col:
            return self.get_prefs(user_id)
        table = self._prefs_table()
        bool_val = value if self._postgres else (1 if value else 0)
        if self._postgres:
            self._execute(
                f"""
                INSERT INTO {table} (user_id, {col}) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET {col} = EXCLUDED.{col}
                """,
                (user_id, bool_val),
            )
        else:
            self._execute(
                f"INSERT INTO {table} (user_id, {col}) VALUES (?, ?) "
                f"ON CONFLICT(user_id) DO UPDATE SET {col} = excluded.{col}",
                (user_id, bool_val),
            )
        return self.get_prefs(user_id)
