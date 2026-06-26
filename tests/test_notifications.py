"""Notifications tests."""

from fastapi.testclient import TestClient

from raphael_notifications.app import app
from raphael_notifications.postmark import PostmarkClient


def test_health() -> None:
    client = TestClient(app)
    assert client.get("/health").json()["service"] == "raphael-notifications"


def test_postmark_skips_without_token() -> None:
    client = PostmarkClient(token="")
    result = client.send("a@b.com", "Hi", "<p>Hi</p>")
    assert result["status"] == "skipped"


def test_event_ingest() -> None:
    client = TestClient(app)
    res = client.post(
        "/v1/notifications/events",
        json={"type": "raphael.reviews.created", "data": {"title": "Test", "assignee": "usr_1", "email": "t@t.com"}},
    )
    assert res.status_code == 200
