"""Audit 2026-11-27, batch 4 (docs/audit/05_ISSUES_AND_RECOMMENDATIONS.md): accounts.

SR-01  the first Google sign-in into an account that was created with a password ends that password and its sessions
SR-03  the e-mails of the sign-in flows leave after the commit, never inside the request's transaction
"""
import time

from app.db.session import _factory
from app.integrations.mailer import ConsoleMailer
from app.services.auth import AuthService
from tests.conftest import PASSWORD, login, make_account
from tests.test_api_google_login import _post, google  # noqa: F401
from tests.test_api_orders import API, _sql


# ---------------------------------------------------------------------------------------------- SR-01
def test_the_first_google_sign_in_ends_a_password_somebody_else_may_have_set(client, google, mailbox):  # noqa: F811
    email = make_account("CUSTOMER")                      # whoever registered first chose this password...
    squatter = login(client, email)                       # ...and is signed in with it
    sq_h = {"Authorization": f"Bearer {squatter['access_token']}"}
    assert client.get(f"{API}/me", headers=sq_h).status_code == 200

    google(email, "Chủ Thật")                             # the owner of the address arrives through Google
    r = _post(client)
    assert r.status_code == 200, r.text
    owner_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"{API}/me", headers=owner_h).status_code == 200

    assert client.get(f"{API}/me", headers=sq_h).status_code == 401                                   # the old session is gone
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": squatter["refresh_token"]}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401   # so is the password
    acc = _sql("select id from accounts where email=:e", e=email)
    assert _sql("select count(*) from audit_logs where action='ACCOUNT_GOOGLE_LINK' and entity_id=:a", a=acc) == 1
    told = [m for m in mailbox if m[0] == email]
    assert len(told) == 1 and "Google" in told[0][1] and "Quên mật khẩu" in told[0][2]                 # the owner is told why


def test_later_google_sign_ins_leave_the_password_and_the_other_devices_alone(client, google, mailbox):  # noqa: F811
    email = make_account("CUSTOMER")
    google(email, "Chủ Thật")
    first = _post(client).json()
    # the owner sets a password of their own afterwards (the reset goes to the same address Google vouched for)
    with _factory()() as s:
        svc = AuthService(s, ConsoleMailer())
        svc._set_password(svc.repo.get_by_email(email), "MatKhauMoi#2026")
        s.commit()
    phone = login(client, email, "MatKhauMoi#2026")
    mailbox.clear()

    again = _post(client)
    assert again.status_code == 200
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {phone['access_token']}"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": email, "password": "MatKhauMoi#2026"}).status_code == 200
    assert _sql("select count(*) from audit_logs where action='ACCOUNT_GOOGLE_LINK' and entity_id=:a", a=first["account"]["id"]) == 1
    assert mailbox == []


def test_an_account_born_from_google_is_never_reset_by_google(client, google, mailbox):  # noqa: F811
    from tests.conftest import fresh_email
    email = fresh_email()
    google(email, "Lê Thị Mai")
    one = _post(client).json()
    mailbox.clear()
    two = _post(client)
    assert two.status_code == 200
    assert client.get(f"{API}/me", headers={"Authorization": f"Bearer {one['access_token']}"}).status_code == 200   # still signed in
    assert _sql("select count(*) from audit_logs where action='ACCOUNT_GOOGLE_LINK' and entity_id=:a", a=one["account"]["id"]) == 0
    assert mailbox == []


# ---------------------------------------------------------------------------------------------- SR-03
class _SlowMailer:
    """Stands for real SMTP: takes a while, and records from which thread and at what moment it was asked to send."""

    def __init__(self):
        self.sent, self.started = [], []

    def send(self, to, subject, body):
        import threading
        self.started.append(threading.current_thread().name)
        time.sleep(0.4)
        self.sent.append(to)


def test_the_reset_mail_is_sent_after_the_commit_and_off_the_request(client):
    email = make_account("CUSTOMER")
    mailer = _SlowMailer()
    with _factory()() as s:
        t0 = time.monotonic()
        AuthService(s, mailer).request_password_reset(email)
        asked = time.monotonic() - t0
        assert mailer.started == []                      # nothing left while the transaction was still open
        s.commit()
        committed = time.monotonic() - t0
    assert asked < 0.3 and committed < 0.3               # an address that exists answers as fast as one that does not
    deadline = time.monotonic() + 3
    while not mailer.sent and time.monotonic() < deadline:
        time.sleep(0.02)
    assert mailer.sent == [email] and mailer.started == ["auth-mail"]


def test_a_rolled_back_reset_sends_nothing(client):
    email = make_account("CUSTOMER")
    mailer = _SlowMailer()
    with _factory()() as s:
        AuthService(s, mailer).request_password_reset(email)
        s.rollback()
    time.sleep(0.2)
    assert mailer.started == []
