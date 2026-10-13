"""Email port. Real SMTP adapter is deferred (UC-49); ConsoleMailer is the dev/test adapter."""
import logging
from typing import Protocol

log = logging.getLogger("app.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer:
    """Logs the message and keeps it in `outbox` so tests can read it."""

    outbox: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append((to, subject, body))
        log.info("MAIL to=%s subject=%s", to, subject)


_mailer: Mailer = ConsoleMailer()


def get_mailer() -> Mailer:
    return _mailer
