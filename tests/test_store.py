"""Notifications store domain tests."""

from pathlib import Path

import pytest

from raphael_notifications.store import NotificationsStore


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> NotificationsStore:
    monkeypatch.delenv("RAPHAEL_DATABASE_URL", raising=False)
    return NotificationsStore(db_path=tmp_path / "notifications.db")


def test_add_and_list_notification(store: NotificationsStore) -> None:
    created = store.add("usr_1", "raphael.reviews.created", "New review", body="Please review")
    listed = store.list_for_user("usr_1")
    assert any(n["id"] == created["id"] for n in listed)
    assert listed[0]["read"] is False


def test_mark_read(store: NotificationsStore) -> None:
    created = store.add("usr_2", "raphael.mentions.created", "Mention")
    result = store.mark_read("usr_2", created["id"])
    assert result is not None
    assert result["read"] is True
    unread = store.list_for_user("usr_2", unread_only=True)
    assert not any(n["id"] == created["id"] for n in unread)


def test_preferences_roundtrip(store: NotificationsStore) -> None:
    defaults = store.get_prefs("usr_prefs")
    assert defaults["emailDigest"] is True
    updated = store.set_pref("usr_prefs", "smsAlerts", True)
    assert updated["smsAlerts"] is True
    assert store.get_prefs("usr_prefs")["smsAlerts"] is True


def test_notifications_persist_across_instances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RAPHAEL_DATABASE_URL", raising=False)
    db = tmp_path / "notifications-persist.db"
    store1 = NotificationsStore(db_path=db)
    store1.add("usr_persist", "test.event", "Persisted")
    store2 = NotificationsStore(db_path=db)
    assert len(store2.list_for_user("usr_persist")) >= 1
