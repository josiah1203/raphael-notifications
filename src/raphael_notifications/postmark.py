"""Postmark email delivery — no custom SMTP."""

from __future__ import annotations

import os
from typing import Any

import httpx


class PostmarkClient:
    def __init__(self, token: str | None = None, from_email: str | None = None) -> None:
        self.token = token or os.environ.get("RAPHAEL_NOTIFICATIONS_POSTMARK_TOKEN", "")
        self.from_email = from_email or os.environ.get(
            "RAPHAEL_NOTIFICATIONS_FROM_EMAIL", "notifications@raphael.app"
        )

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def send(self, to: str, subject: str, html_body: str, text_body: str | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "skipped", "reason": "no_postmark_token", "to": to, "subject": subject}
        payload = {
            "From": self.from_email,
            "To": to,
            "Subject": subject,
            "HtmlBody": html_body,
            "TextBody": text_body or html_body,
            "MessageStream": "outbound",
        }
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                "https://api.postmarkapp.com/email",
                json=payload,
                headers={"X-Postmark-Server-Token": self.token, "Accept": "application/json"},
            )
            if res.status_code >= 400:
                return {"status": "error", "code": res.status_code, "body": res.text}
            return {"status": "sent", **res.json()}
