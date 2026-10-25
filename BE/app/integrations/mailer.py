"""Email port. ConsoleMailer is the dev/test adapter; SmtpMailer sends for real when SMTP_HOST is configured."""
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger("app.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer:
    """Logs the message and keeps it in `outbox` so tests can read it."""

    outbox: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.outbox.append((to, subject, body))
        log.info("MAIL to=%s subject=%s", to, subject)


class SmtpMailer:
    """Plain SMTP with STARTTLS. Failures are raised to the caller, which decides whether they matter (alerts only log them)."""

    def __init__(self, host: str, port: int, user: str | None, password: str | None, sender: str, starttls: bool = True,
                 timeout: float = 10.0, factory=smtplib.SMTP):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.starttls, self.timeout, self.factory = sender, starttls, timeout, factory

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"], msg["Date"] = self.sender, to, subject, formatdate(localtime=False)
        msg.set_content(body)
        with self.factory(self.host, self.port, timeout=self.timeout) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.user and self.password:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)
        log.info("MAIL sent to=%s subject=%s", to, subject)


_mailer: Mailer = ConsoleMailer()


def get_mailer() -> Mailer:
    s = get_settings()
    if s.smtp_host and (s.smtp_from or s.smtp_user):
        return SmtpMailer(s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password, s.smtp_from or s.smtp_user or "",
                          s.smtp_starttls, s.smtp_timeout_seconds)
    return _mailer
