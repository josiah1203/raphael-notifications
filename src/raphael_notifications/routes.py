"""Notifications API + event handlers."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException

from raphael_notifications.postmark import PostmarkClient
from raphael_notifications.store import NotificationsStore
from raphael_notifications.twilio_sms import TwilioSmsClient

router = APIRouter(tags=["notifications"])
_store = NotificationsStore()
_postmark = PostmarkClient()
_sms = TwilioSmsClient()


def _maybe_send_sms(phone: str | None, body: str, prefs: dict[str, bool], gate: str) -> None:
    if not phone or not prefs.get("smsAlerts", False) or not prefs.get(gate, False):
        return
    _sms.send(phone, body)


def _notify_user(
    user_id: str,
    email: str,
    phone: str | None,
    prefs: dict[str, bool],
    event_type: str,
    title: str,
    summary: str,
    data: dict[str, Any],
    *,
    email_html: str | None = None,
    sms_gate: str | None = None,
    sms_body: str | None = None,
) -> None:
    _store.add(user_id, event_type, title, summary, data)
    if prefs.get("reviewAlerts", True) or event_type.startswith("raphael.automations"):
        _postmark.send(email, title, email_html or f"<p>{summary}</p>", summary)
    if sms_gate and sms_body:
        _maybe_send_sms(phone, sms_body, prefs, sms_gate)


def _handle_review_created(data: dict[str, Any], prefs: dict[str, bool]) -> None:
    user_id = data.get("assignee") or data.get("user_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    phone = data.get("phone")
    title = f"Review requested: {data.get('title', 'Review')}"
    summary = data.get("summary", "")
    _notify_user(user_id, email, phone, prefs, "raphael.reviews.created", title, summary, data, sms_gate="smsReviewAlerts", sms_body=f"{title}. {summary}".strip())


def _handle_review_merged(data: dict[str, Any], prefs: dict[str, bool]) -> None:
    user_id = data.get("assignee") or data.get("user_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    title = f"Review merged: {data.get('review_id', 'Review')}"
    summary = data.get("message", "Changes merged to target branch.")
    _notify_user(user_id, email, None, prefs, "raphael.reviews.merged", title, summary, data)


def _handle_workspace_commit(data: dict[str, Any], prefs: dict[str, bool]) -> None:
    if not prefs.get("reviewAlerts", True):
        return
    user_id = data.get("actor_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    module_id = data.get("module_id", "module")
    title = f"Commit on {module_id}"
    summary = data.get("message", "")
    _notify_user(user_id, email, None, prefs, "raphael.workspaces.commit", title, summary, data)


def _handle_workspace_merge(data: dict[str, Any], prefs: dict[str, bool]) -> None:
    if not prefs.get("reviewAlerts", True):
        return
    user_id = data.get("actor_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    module_id = data.get("module_id", "module")
    title = f"Merged {data.get('source')} → {data.get('target')} on {module_id}"
    _notify_user(user_id, email, None, prefs, "raphael.workspaces.merge", title, "", data)


def _handle_automation_failed(data: dict[str, Any], prefs: dict[str, bool]) -> None:
    user_id = data.get("user_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    phone = data.get("phone")
    title = f"Automation failed: {data.get('name', 'Pipeline')}"
    body = data.get("error", "Check the automation run for details.")
    _notify_user(
        user_id,
        email,
        phone,
        prefs,
        "raphael.automations.failed",
        title,
        body,
        data,
        sms_gate="smsAutomationFailures",
        sms_body=f"{title}. {body}",
    )


def _handle_org_invite(data: dict[str, Any], prefs: dict[str, bool]) -> None:
    user_id = data.get("user_id") or "usr_default"
    email = data.get("email", f"{user_id}@example.com")
    title = "You've been invited to a workspace"
    _notify_user(user_id, email, None, prefs, "raphael.orgs.invite.created", title, "", data, email_html="<p>Click to accept your invite.</p>")


_EVENT_ROUTES: dict[str, Callable[[dict[str, Any], dict[str, bool]], None]] = {
    "raphael.reviews.created": _handle_review_created,
    "raphael.reviews.merged": _handle_review_merged,
    "raphael.workspaces.commit": _handle_workspace_commit,
    "raphael.workspaces.merge": _handle_workspace_merge,
    "raphael.automations.failed": _handle_automation_failed,
    "raphael.orgs.invite.created": _handle_org_invite,
}


def handle_event(event_type: str, data: dict[str, Any]) -> None:
    """Route platform events to in-app + email + SMS channels."""
    handler = _EVENT_ROUTES.get(event_type)
    if not handler:
        return
    user_id = data.get("assignee") or data.get("user_id") or "usr_default"
    prefs = _store.get_prefs(user_id)
    if event_type == "raphael.reviews.created" and not prefs.get("reviewAlerts", True):
        return
    if event_type == "raphael.orgs.invite.created" and not prefs.get("inviteAlerts", True):
        return
    handler(data, prefs)


@router.get("")
def list_notifications(x_raphael_user_id: str | None = Header(default="usr_default")) -> dict[str, list]:
    return {"notifications": _store.list_for_user(x_raphael_user_id or "usr_default")}


@router.patch("/{notification_id}")
def mark_read(
    notification_id: str,
    x_raphael_user_id: str | None = Header(default="usr_default"),
) -> dict[str, Any]:
    user_id = x_raphael_user_id or "usr_default"
    result = _store.mark_read(user_id, notification_id)
    if not result:
        raise HTTPException(404, detail="not_found")
    return result


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
