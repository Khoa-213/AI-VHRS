"""Phase 5a: background jobs. Real database; every job runs SCOPED to the test's own orders (`order_ids`), so the real orders of
the shared database are never touched. Each job is checked twice: the second run must do nothing more."""
from sqlalchemy import text

from app.db.session import _factory, get_engine
from app.integrations.storage import InMemoryStorage
from app.services import background_jobs as bj
from app.services import notifications as ns
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _deposit, _quoted
from tests.test_api_photos_acceptance import _awaiting
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _user, cust, policy, staff, store, wcat  # noqa: F401


def _run(job, oid, **kw):
    with _factory()() as s:
        return bj.JOBS[job](s, order_ids=[oid], **kw)


def _status(oid):
    return _sql("select order_status::text from orders where id=:o", o=oid)


def _notes(oid, code=None):
    return _sql("select count(*) from notifications where order_id=:o and channel='IN_APP'" +
                (" and title like :t" if code else ""), o=oid, **({"t": f"%{code}%"} if code else {}))


def test_an_overdue_quotation_expires_and_cancels_the_order(client, cust, staff, wcat):
    oid, q = _quoted(client, cust, staff[0], wcat)
    assert _run("quotation_expiry", oid) == {"expired": 0}                            # still valid
    _sql("update quotations set sent_at = now() - interval '9 days', valid_until = now() - interval '1 minute' where order_id=:o and status='SENT' returning 1", o=oid)
    assert _run("quotation_expiry", oid) == {"expired": 1}
    assert _status(oid) == "CANCELLED"
    assert _sql("select count(*) from notifications where order_id=:o and msg_code='MSG08' and channel='IN_APP'", o=oid) == 1
    assert _run("quotation_expiry", oid) == {"expired": 0}


def test_an_unpaid_order_is_cancelled_after_the_deposit_deadline(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    assert _run("deposit_deadline", oid)["cancelled"] == 0                           # approved just now
    _sql("update quotations set customer_responded_at = now() - interval '4 days' where order_id=:o and status='APPROVED' "
         "returning 1", o=oid)
    pay = _deposit(client, cust, oid)                                                  # the customer is paying right now
    r = _run("deposit_deadline", oid)
    assert r["cancelled"] == 0 and r["days"] == 3 and _status(oid) == "AWAITING_DEPOSIT"
    _sql("update payments set created_at = now() - interval '2 hours' where id=:p returning 1", p=pay["id"])
    assert _run("deposit_deadline", oid)["cancelled"] == 1
    assert _status(oid) == "CANCELLED"
    assert _sql("select status::text from payments where id=:p", p=pay["id"]) == "CANCELLED"
    assert _sql("select cancel_reason from orders where id=:o", o=oid).startswith("Quá hạn đặt cọc")
    assert _notes(oid, "quá hạn cọc") == 1
    assert _run("deposit_deadline", oid)["cancelled"] == 0


def test_acceptance_reminder_once_then_auto_accept(client, cust, staff, mgr, wcat, robot, tech, store):
    oid, jid = _awaiting(client, cust, staff, mgr, wcat, robot, tech, store)
    assert _run("acceptance", oid) == {"auto_accepted": 0, "reminded": 0}
    _sql("update orders set awaiting_acceptance_at = now() - interval '4 days' where id=:o returning 1", o=oid)
    assert _run("acceptance", oid) == {"auto_accepted": 0, "reminded": 1}
    assert _run("acceptance", oid) == {"auto_accepted": 0, "reminded": 0}               # only once
    assert _notes(oid, "Nhắc nghiệm thu") == 1
    _sql("update orders set awaiting_acceptance_at = now() - interval '8 days' where id=:o returning 1", o=oid)
    assert _run("acceptance", oid) == {"auto_accepted": 1, "reminded": 0}
    assert _status(oid) == "AWAITING_FINAL_PAYMENT"
    assert _run("acceptance", oid) == {"auto_accepted": 0, "reminded": 0}


def test_failed_emails_are_sent_again(client, cust, staff, wcat, monkeypatch, mailbox):
    oid, q = _quoted(client, cust, staff[0], wcat)
    uid = client.get(f"{API}/me", headers=cust).json()["id"]

    class Broken:
        def send(self, *a):
            raise OSError("smtp down")
    with monkeypatch.context() as m:
        m.setattr(ns, "get_mailer", lambda: Broken())
        with _factory()() as s:
            ns.notify(s, account_id=uid, order_id=oid, msg_code="MSG12", code="RETRY")
            s.commit()
    row = "select count(*) from notifications where order_id=:o and channel='EMAIL' and title like '%RETRY%' and sent_at is null"
    assert _sql(row, o=oid) == 1
    assert _run("email_retry", oid) == {"tried": 0, "sent": 0}                        # too young: the first try may still run
    _sql("update notifications set created_at = now() - interval '10 minutes' where order_id=:o and channel='EMAIL' returning 1",
         o=oid)
    mailbox.clear()
    r = _run("email_retry", oid)
    assert r["sent"] >= 1 and _sql(row, o=oid) == 0 and any("RETRY" in m[2] for m in mailbox)
    assert _run("email_retry", oid)["tried"] == 0


def _input(oid, kind, path, style_id=None):
    return _sql("""insert into order_inputs (order_id, kind, file_url, mime_type, file_size_bytes, handwriting_style_id)
                   values (:o, cast(:k as order_input_kind), :p, 'image/jpeg', 1000, :s) returning id""",
                o=oid, k=kind, p=path, s=style_id)


def test_customer_photos_are_purged_after_90_days_only_when_enabled(client, cust, staff, wcat, monkeypatch):
    oid, q = _quoted(client, cust, staff[0], wcat)
    uid = client.get(f"{API}/me", headers=cust).json()["id"]
    kept_style = _sql("""insert into handwriting_styles (owner_id, name, status, right_to_use_confirmed, keep_consent)
                         values (:u, 'pytest kept', 'APPROVED', true, true) returning id""", u=uid)
    img = _input(oid, "ORIGINAL_IMAGE", f"pytest/{oid}/a.jpg")
    kept = _input(oid, "HANDWRITING_SAMPLE", f"pytest/{oid}/b.jpg", kept_style)
    store = InMemoryStorage()
    store.put(f"pytest/{oid}/a.jpg", b"x")
    store.put(f"pytest/{oid}/b.jpg", b"y")
    monkeypatch.setattr(bj, "PURGE_AFTER_DAYS", 0)                                     # "90 days ago" = now
    assert _run("photo_purge", oid, storage=store, enabled=True)["deleted"] == 0       # the order is still open
    assert client.post(f"{API}/orders/{oid}/cancel", headers=cust, json={"reason": "pytest"}).status_code == 200
    assert _run("photo_purge", oid, storage=store) == {"dry_run": True, "would_delete": 1, "storage": True}   # setting off
    assert _run("photo_purge", oid, storage=store, enabled=True) == {"dry_run": False, "deleted": 1, "failed": 0}
    assert f"pytest/{oid}/a.jpg" not in store.objects and f"pytest/{oid}/b.jpg" in store.objects   # kept with consent
    assert _sql("select deleted_at is not null from order_inputs where id=:i", i=img) is True
    assert _sql("select deleted_at is null from order_inputs where id=:i", i=kept) is True
    assert _run("photo_purge", oid, storage=store, enabled=True)["deleted"] == 0


def test_the_runner_never_overlaps_and_keeps_going_after_an_error(client, cust, staff, wcat, monkeypatch):
    oid, q = _quoted(client, cust, staff[0], wcat)
    with get_engine().connect() as c:                                                  # another run holds the lock
        assert c.execute(text("select pg_try_advisory_lock(:k)"), {"k": bj.LOCK_KEY}).scalar()
        try:
            assert bj.run_all(order_ids=[oid])["ran"] is False
        finally:
            c.execute(text("select pg_advisory_unlock(:k)"), {"k": bj.LOCK_KEY})
            c.commit()

    def boom(session, **kw):
        raise RuntimeError("bad job")
    monkeypatch.setitem(bj.JOBS, "acceptance", boom)
    out = bj.run_all(order_ids=[oid], storage=InMemoryStorage())
    assert out["ran"] is True and set(out["results"]) == set(bj.JOBS)
    assert "bad job" in out["results"]["acceptance"]["error"]
    assert out["results"]["quotation_expiry"] == {"expired": 0} and out["results"]["photo_purge"]["dry_run"] is True


def test_admin_runs_the_jobs_now(client, monkeypatch):
    admin, _ = _user(client, "ADMIN")
    calls = []
    monkeypatch.setattr(bj, "run_all", lambda **kw: calls.append(kw) or {
        "ran": True, "results": {"email_retry": {"tried": 0, "sent": 0}}, "started_at": "2026-11-06T00:00:00+00:00",
        "seconds": 0.1})
    assert client.post(f"{API}/admin/jobs/run", headers=admin, json={}).status_code == 422          # confirm required
    r = client.post(f"{API}/admin/jobs/run", headers=admin, json={"confirm": True, "only": ["email_retry"]})
    assert r.status_code == 200 and r.json()["ran"] is True and calls[0]["only"] == ["email_retry"]
    assert client.post(f"{API}/admin/jobs/run", headers=admin, json={"confirm": True, "only": ["nope"]}).status_code == 422
    assert client.get(f"{API}/admin/jobs/last", headers=admin).status_code == 200
