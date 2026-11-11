"""SMS providers behind one switch (SMS_PROVIDER in .env).

    outbox  (default) - nothing leaves your computer. Texts land in the 'fake phone' screen. Free.
    twilio            - real texts through Twilio. Needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM.

Adding WhatsApp or another provider later = one more class with the same send() method.
"""
from dataclasses import dataclass

import httpx

from app.core.config import get_settings


@dataclass
class SendResult:
    status: str  # simulated | queued | failed
    provider: str
    provider_message_id: str | None = None
    error: str | None = None


class OutboxProvider:
    name = "outbox"

    def send(self, to: str, body: str) -> SendResult:
        return SendResult(status="simulated", provider=self.name)


class TwilioProvider:
    name = "twilio"

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    def send(self, to: str, body: str) -> SendResult:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        try:
            r = httpx.post(url, data={"To": to, "From": self.from_number, "Body": body},
                           auth=(self.account_sid, self.auth_token), timeout=10)
        except httpx.HTTPError as e:
            return SendResult(status="failed", provider=self.name, error=type(e).__name__)
        if r.status_code >= 300:
            return SendResult(status="failed", provider=self.name, error=f"HTTP {r.status_code}")
        return SendResult(status="queued", provider=self.name, provider_message_id=r.json().get("sid"))


def get_sms_provider():
    s = get_settings()
    if s.sms_provider == "twilio":
        if not (s.twilio_account_sid and s.twilio_auth_token and s.twilio_from):
            raise RuntimeError("SMS_PROVIDER=twilio needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM")
        return TwilioProvider(s.twilio_account_sid, s.twilio_auth_token, s.twilio_from)
    return OutboxProvider()
