"""SMS port (Phase 5e, FR-53 OTP).

SMS_MODE=mock (default and, for now, the only mode): nothing leaves the server. The message is kept in `MockSms.outbox`
(tests read the code there) and the log gets the masked number only, never the text, so a code never lands in a log.
A real provider (eSMS, SpeedSMS, Twilio...) is one more class with the same `send`, added when the project owner picks one.
"""
import logging
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger("app.sms")


class SmsSender(Protocol):
    mode: str

    def send(self, phone: str, text: str) -> None: ...


def mask(phone: str) -> str:
    return phone[:3] + "****" + phone[-3:] if len(phone) > 6 else "****"


class MockSms:
    mode = "MOCK"
    outbox: list[tuple[str, str]] = []

    def send(self, phone: str, text: str) -> None:
        self.outbox.append((phone, text))
        log.info("SMS mode=MOCK to=%s (not sent)", mask(phone))


_mock = MockSms()


def get_sms_sender() -> SmsSender:
    get_settings()          # sms_mode is validated by the settings (only "mock" exists today)
    return _mock
