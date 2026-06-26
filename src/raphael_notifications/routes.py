"""Notifications API + event handlers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from raphael_notifications.postmark import PostmarkClient
from raphael_notifications.store import NotificationsStore

router = APIRouter(tags=["notifications"])
_store = NotificationsStore()
_postmark = PostmarkClient()


def handle_event(event_type: str, data: dict[str, Any]) -> None:
    """Route platform events to in-app + email channels."""
    user_id = data.get("assignee") or data.get("user_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    prefs = _store.get_prefs(user_id)

    if event_type == "raphael.reviews.created" and prefs.get("reviewAlerts", True):
        title = f"Review requested: {data.get('title', 'Review')}"
        _store.add(user_id, event_type, title, data.get("summary", ""), data)
        _postmark.send(email, title, f"<p>{data.get('summary', '')}</p>", data.get("summary"))

    if event_type == "raphael.orgs.invite.created" and prefs.get("inviteAlerts", True):
        title = "You've been invited to a workspace"
        _store.add(user_id, event_type, title, "", data)
        _postmark.send(email, title, "<p>Click to accept your invite.</p>", "You've been invited.")


@router.get("")
def list_notifications(x_raphael_user_id: str | None = Header(default="usr_default")) -> dict[str, list]:
    return {"notifications": _store.list_for_user(x_raphael_user_id or "usr_default")}


@router.get("/preferences")
def get_preferences(x_raphael_user_id: str | None = Header(default="usr_default")) -> dict[str, bool]:
    return _store.get_prefs(x_raphael_user_id or "usr_default")


@router.patch("/preferences")
def patch_preferences(body: dict[str, Any], x_raphael_user_id: str | None = Header(default="usr_default")) -> dict[str, bool]:
    user_id = x_raphael_user_id or "usr_default"
    prefs = _store.get_prefs(user_id)
    for key, val in body.items():
        if isinstance(val, bool):
            prefs = _store.set_pref(user_id, key, val)
    return prefs


@router.post("/events")
def ingest_event(body: dict[str, Any]) -> dict[str, str]:
    """Internal: consume event bus messages (HTTP hook for dev without Kafka)."""
    handle_event(body.get("type", ""), body.get("data", {}))
    return {"status": "processed"}
