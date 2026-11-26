"""Email port. ConsoleMailer is the dev/test adapter; SmtpMailer sends for real when SMTP_HOST is configured.

SmtpMailer sends the text as text/plain plus an HTML alternative with the AI-VHRS logo inline (`mail_html`), and a
`Reply-To` when SMTP_REPLY_TO is set (the From must be on the verified sending domain; replies go to the project mailbox)."""
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from app.core.config import get_settings
from app.integrations import mail_html

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
                 timeout: float = 10.0, factory=smtplib.SMTP, reply_to: str | None = None, html: bool = True):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.starttls, self.timeout, self.factory = sender, starttls, timeout, factory
        self.reply_to, self.html = (reply_to or "").strip() or None, html

    def build(self, to: str, subject: str, body: str) -> EmailMessage:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"], msg["Date"] = self.sender, to, subject, formatdate(localtime=False)
        domain = self.sender.rsplit("@", 1)[-1].strip(" >") if "@" in self.sender else None
        msg["Message-ID"] = make_msgid(domain=domain or None)
        if self.reply_to:
            msg["Reply-To"] = self.reply_to
        msg.set_content(body)
        if self.html:
            images = mail_html.inline_images()
            msg.add_alternative(mail_html.render(body, subject, with_logo=bool(images), with_dark_logo=len(images) > 1),
                                subtype="html")
            for cid, png in images:              # multipart/alternative > multipart/related(html, logos)
                msg.get_payload()[1].add_related(png, "image", "png", cid=f"<{cid}>", filename=f"{cid}.png",
                                                 disposition="inline")
        return msg

    def send(self, to: str, subject: str, body: str) -> None:
        msg = self.build(to, subject, body)
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
                          s.smtp_starttls, s.smtp_timeout_seconds, reply_to=s.smtp_reply_to, html=s.smtp_html)
    return _mailer
