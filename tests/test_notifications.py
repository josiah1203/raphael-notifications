"""Notifications tests."""

import uuid

from fastapi.testclient import TestClient

from raphael_notifications.app import app
from raphael_notifications.postmark import PostmarkClient
from raphael_notifications.twilio_sms import TwilioSmsClient


def test_health() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["service"] == "raphael-notifications"


def test_list_empty_for_new_user() -> None:
    client = TestClient(app)
    user_id = f"usr_empty_{uuid.uuid4().hex[:8]}"
    notifications = client.get("/v1/notifications", headers={"X-Raphael-User-Id": user_id}).json()[
        "notifications"
    ]
    assert notifications == []


def test_postmark_skips_without_token() -> None:
    client = PostmarkClient(token="")
    result = client.send("a@b.com", "Hi", "<p>Hi</p>")
    assert result["status"] == "skipped"


def test_twilio_skips_without_config() -> None:
    client = TwilioSmsClient(account_sid="", auth_token="", from_number="")
    result = client.send("+15555550100", "Hi")
    assert result["status"] == "skipped"


def test_event_ingest() -> None:
    client = TestClient(app)
    res = client.post(
        "/v1/notifications/events",
        json={"type": "raphael.reviews.created", "data": {"title": "Test", "assignee": "usr_1", "email": "t@t.com"}},
    )
    assert res.status_code == 200


def test_merge_event_ingest() -> None:
    client = TestClient(app)
    res = client.post(
        "/v1/notifications/events",
        json={
            "type": "raphael.reviews.merged",
            "data": {"review_id": "pr-1", "assignee": "usr_merge", "email": "m@t.com"},
        },
    )
    assert res.status_code == 200
    notifications = client.get("/v1/notifications", headers={"X-Raphael-User-Id": "usr_merge"}).json()[
        "notifications"
    ]
    assert any(n["type"] == "raphael.reviews.merged" for n in notifications)


def test_sms_prefs_defaults() -> None:
    client = TestClient(app)
    prefs = client.get("/v1/notifications/preferences", headers={"X-Raphael-User-Id": "usr_sms_test"}).json()
    assert prefs["smsAlerts"] is False
    assert prefs["smsReviewAlerts"] is False
    assert prefs["smsAutomationFailures"] is False


def test_mark_read() -> None:
    client = TestClient(app)
    headers = {"X-Raphael-User-Id": "usr_mark_read"}
    client.post(
        "/v1/notifications/events",
        json={"type": "raphael.reviews.created", "data": {"title": "Read me", "assignee": "usr_mark_read"}},
    )
    notifications = client.get("/v1/notifications", headers=headers).json()["notifications"]
    assert notifications
    nid = notifications[0]["id"]
    assert notifications[0]["read"] is False
    res = client.patch(f"/v1/notifications/{nid}", headers=headers)
    assert res.status_code == 200
    assert res.json()["read"] is True


def test_mark_read_not_found() -> None:
    client = TestClient(app)
    res = client.patch(
        "/v1/notifications/nid-does-not-exist",
        headers={"X-Raphael-User-Id": "usr_missing"},
    )
    assert res.status_code == 404
