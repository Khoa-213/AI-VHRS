"""SMTP adapter against a fake SMTP object (nothing is sent anywhere). Pure, no database."""
from app.integrations import mail_html
from app.integrations.mailer import SmtpMailer


class FakeSMTP:
    log: list = []
    sent: list = []

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
        self.sent.append(msg)
        text = msg.get_body(("plain",)).get_content().strip()
        self.log.append(("send", msg["To"], msg["Subject"], msg["From"], text))


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


BODY = ("Xin chào,\n\nMã đặt lại mật khẩu AI-VHRS của bạn là: 482913\n\n"
        "Hoặc bấm liên kết sau để đặt mật khẩu mới:\nhttps://www.example.com/reset-password?token=a&b=1\n\n"
        "Xem đơn tại https://www.example.com/orders/7 <script>\n\nXưởng Nét Việt")


def test_html_part_with_the_inline_logo_and_reply_to():
    m = SmtpMailer("h", 2587, None, None, "Xưởng Nét Việt <no-reply@mail.example.com>", factory=FakeSMTP,
                   reply_to="project@example.com").build("c@example.com", "Mã đặt lại mật khẩu", BODY)
    assert m["Reply-To"] == "project@example.com"
    assert m["Message-ID"].endswith("@mail.example.com>")
    assert m.get_content_type() == "multipart/alternative"
    assert m.get_body(("plain",)).get_content().strip() == BODY            # the text is unchanged for text-only clients
    page = m.get_body(("html",)).get_content()
    assert f'src="cid:{mail_html.LOGO_CID}"' in page
    assert "letter-spacing:8px" in page and ">482913</div>" in page                    # the code, large
    assert 'href="https://www.example.com/reset-password?token=a&amp;b=1"' in page and mail_html.BUTTON_LABEL in page
    assert '<a href="https://www.example.com/orders/7"' in page and "&lt;script&gt;" in page and "<script>" not in page
    logo = [p for p in m.walk() if p.get_content_type() == "image/png"]
    assert len(logo) == 1 and logo[0]["Content-ID"] == f"<{mail_html.LOGO_CID}>"
    assert logo[0].get_content_disposition() == "inline" and logo[0].get_content() == mail_html.logo_bytes()


def test_no_reply_to_and_plain_text_only_when_switched_off():
    m = SmtpMailer("h", 25, None, None, "a@b.c", factory=FakeSMTP, reply_to="  ", html=False).build("x@y.z", "s", "b")
    assert m["Reply-To"] is None and m.get_content_type() == "text/plain"
