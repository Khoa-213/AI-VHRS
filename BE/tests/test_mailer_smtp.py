"""SMTP adapter against a fake SMTP object (nothing is sent anywhere). Pure, no database."""
from app.integrations.mailer import SmtpMailer


class FakeSMTP:
    log: list = []

    def __init__(self, host, port, timeout=None):
        self.log.append(("connect", host, port, timeout))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.log.append(("quit",))

    def starttls(self):
        self.log.append(("starttls",))

    def login(self, u, p):
        self.log.append(("login", u))

    def send_message(self, msg):
        self.log.append(("send", msg["To"], msg["Subject"], msg["From"], msg.get_content().strip()))


def test_smtp_mailer_uses_starttls_then_login_then_sends_utf8():
    FakeSMTP.log.clear()
    SmtpMailer("smtp.example.com", 587, "user", "app-password", "robot@example.com", factory=FakeSMTP).send(
        "tech@example.com", "[KHẨN - BẤM E-STOP] Robot FR3-01", "Bấm nút E-Stop ngay.")
    kinds = [e[0] for e in FakeSMTP.log]
    assert kinds == ["connect", "starttls", "login", "send", "quit"]
    sent = FakeSMTP.log[3]
    assert sent[1] == "tech@example.com" and "KHẨN" in sent[2] and sent[3] == "robot@example.com" and sent[4] == "Bấm nút E-Stop ngay."


def test_no_login_without_credentials_and_starttls_can_be_off():
    FakeSMTP.log.clear()
    SmtpMailer("localhost", 25, None, None, "a@b.c", starttls=False, factory=FakeSMTP).send("x@y.z", "s", "b")
    assert [e[0] for e in FakeSMTP.log] == ["connect", "send", "quit"]
