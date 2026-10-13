"""Trigger behaviour on the live schema. Everything runs in one transaction that is rolled back."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.session import get_engine


@pytest.fixture
def tx():
    conn = get_engine().connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


def _upd(c, oid, **cols):
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    c.execute(text(f"update orders set {sets} where id = :id"), {**cols, "id": oid})


def _new_order(c) -> int:
    cust = c.execute(text("select id from accounts where role_id = 1 order by id limit 1")).scalar()
    assert cust, "seed customer missing"
    return c.execute(text("""insert into orders (code, customer_id, order_type, workshop_suggest_materials)
                             values (:c, :u, 'OT3_TEMPLATE', true) returning id"""),
                     {"c": "T" + uuid.uuid4().hex[:8], "u": cust}).scalar()


@pytest.fixture
def writing_order(tx):
    c = tx
    staff = c.execute(text("select id from accounts where role_id = 2 order by id limit 1")).scalar()
    assert staff, "seed staff missing"
    oid = _new_order(c)
    _upd(c, oid, order_status="SUBMITTED")
    _upd(c, oid, order_status="ACCEPTED", assigned_staff_id=staff)
    _upd(c, oid, order_status="AWAITING_PRIVACY")
    c.execute(text("update orders set order_status='QUOTED', privacy_accepted_at=now() where id=:i"), {"i": oid})
    _upd(c, oid, order_status="AWAITING_DEPOSIT")
    _upd(c, oid, order_status="CONFIRMED", production_status="PENDING_SCHEDULE")
    for s in ("SCHEDULED", "PREPARING", "WRITING"):
        _upd(c, oid, production_status=s)
    return oid


def _sqlstate(exc_info) -> str | None:
    return getattr(exc_info.value.orig, "sqlstate", None)


def test_invalid_order_transition_is_conflict(tx):
    oid = _new_order(tx)
    with pytest.raises(DBAPIError) as e:
        _upd(tx, oid, order_status="CONFIRMED")
    assert _sqlstate(e) == "P0409"


def test_cannot_cancel_after_writing_started_without_eta_postponement(tx, writing_order):
    with pytest.raises(DBAPIError) as e:
        _upd(tx, writing_order, order_status="CANCELLED", production_status="NOT_STARTED")
    assert _sqlstate(e) == "P0409"  # BR-14


def test_d1_cancel_allowed_when_eta_postponed_over_7_days(tx, writing_order):
    oid = writing_order
    tx.execute(text("select set_config('app.status_reason', 'robot hỏng', true)"))
    _upd(tx, oid, eta="2026-12-01")
    _upd(tx, oid, eta="2026-12-10")  # +9 days
    assert tx.execute(text("select eta_postponed_days from orders where id=:i"), {"i": oid}).scalar() == 9  # D3
    _upd(tx, oid, order_status="CANCELLED", production_status="NOT_STARTED")  # D1
    row = tx.execute(text("select order_status, production_status from orders where id=:i"), {"i": oid}).one()
    assert tuple(row) == ("CANCELLED", "NOT_STARTED")
    n = tx.execute(text("select count(*) from status_histories where order_id=:i and state_type='ETA'"),
                   {"i": oid}).scalar()
    assert n == 1  # first ETA assignment is not a postponement


def test_eta_change_without_reason_is_rejected(tx, writing_order):
    _upd(tx, writing_order, eta="2026-12-01")
    with pytest.raises(DBAPIError) as e:
        _upd(tx, writing_order, eta="2026-12-05")
    assert _sqlstate(e) == "P0409"  # BR-16
