"""Twilio SMS delivery."""

from __future__ import annotations

import os
from typing import Any


class TwilioSmsClient:
    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
    ) -> None:
        self.account_sid = account_sid or os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.environ.get("TWILIO_PHONE_NUMBER", "")

    @property
    def enabled(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    def send(self, to: str, body: str) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "skipped", "reason": "no_twilio_config", "to": to, "body": body}
        from twilio.rest import Client

        client = Client(self.account_sid, self.auth_token)
        message = client.messages.create(body=body, from_=self.from_number, to=to)
        return {"status": "sent", "sid": message.sid, "to": to}
