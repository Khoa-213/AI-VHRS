"""Stock in and out (migration 0033, owner decisions 2026-11-27 Q1-Q4).

The Manager receives goods on a multi-line receipt; the technician takes a job's paper before Prepare (and a new pen with
its ink only when the pen is replaced); unused paper goes back at Writing done. Every change of `stock_qty` writes one
`stock_movements` row, so the ledger always adds up to the level. Double submits and requests running alongside each
other must not add or take stock twice.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from tests.test_api_manager_ops import _paper, _pen
from tests.test_api_orders import API, _sql, issue_paper
from tests.test_api_technician import _job, _post, _running
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_workshop import _err, _user, cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"
T = f"{API}/technician"


def _ref() -> str:
    return "pytest-" + uuid.uuid4().hex


def _stock(item_kind, item_id):
    table = {"PAPER": "paper_types", "PEN": "pen_types", "INK": "ink_colors"}[item_kind]
    return _sql(f"select stock_qty from {table} where id=:i", i=item_id)


def _ledger_sum(item_kind, item_id):
    return _sql("select coalesce(sum(quantity),0) from stock_movements where item_kind=:k and item_id=:i",
                k=item_kind, i=item_id)


def _overview_row(client, mgr, item_kind, item_id):
    rows = client.get(f"{M}/stock", headers=mgr).json()
    return next(r for r in rows if r["item_kind"] == item_kind and r["item_id"] == item_id)


# ---- access ------------------------------------------------------------------------------------------
def test_stock_endpoints_belong_to_their_roles(client, mgr, tech, staff, cust, wcat):
    body = {"lines": [{"item_kind": "PAPER", "item_id": wcat["paper"], "quantity": 1}]}
    for h in (tech[0], staff[0], cust):
        assert client.get(f"{M}/stock", headers=h).status_code == 403
        assert client.post(f"{M}/stock/receipts", headers=h, json=body).status_code == 403
        assert client.get(f"{M}/stock/movements", headers=h).status_code == 403
    assert client.get(f"{M}/stock").status_code == 401
    assert client.get(f"{T}/jobs/1/stock", headers=mgr).status_code == 403
    assert client.post(f"{T}/jobs/1/stock/issue", headers=mgr, json={"paper": 1, "seen_issued": 0}).status_code == 403


# ---- receipts ----------------------------------------------------------------------------------------
def test_a_receipt_adds_every_line_and_writes_the_ledger(client, mgr):
    p = _paper(client, mgr, stock_qty=10)
    pen = _pen(client, mgr, stock_qty=2)
    ink = client.post(f"{M}/pens/{pen['id']}/inks", headers=mgr,
                      json={"name": "Xanh", "hex_code": "#0000ff", "unit_price": 0, "stock_qty": 0}).json()
    r = client.post(f"{M}/stock/receipts", headers=mgr, json={
        "supplier": " NCC Test ", "note": "Hàng về đợt 1", "client_ref": _ref(),
        "lines": [{"item_kind": "PEN", "item_id": pen["id"], "quantity": 5},
                  {"item_kind": "PAPER", "item_id": p["id"], "quantity": 200},
                  {"item_kind": "INK", "item_id": ink["id"], "quantity": 5}]})
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["created"] is True and rec["code"] == f"NK-{rec['id']:04d}" and rec["supplier"] == "NCC Test"
    assert {(ln["item_kind"], ln["quantity"], ln["stock_after"]) for ln in rec["lines"]} == {
        ("PAPER", 200, 210), ("PEN", 5, 7), ("INK", 5, 5)}
    assert (_stock("PAPER", p["id"]), _stock("PEN", pen["id"]), _stock("INK", ink["id"])) == (210, 7, 5)
    assert client.get(f"{M}/stock/receipts/{rec['id']}", headers=mgr).json()["lines"] == rec["lines"]
    assert client.get(f"{M}/stock/receipts/999999999", headers=mgr).status_code == 404
    assert _sql("select count(*) from audit_logs where action='STOCK_RECEIPT' and entity_id=:i", i=rec["id"]) == 1

    # the ledger adds up to the level: opening count (ADJUST at create) + receipts + corrections
    client.post(f"{M}/papers/{p['id']}/stock", headers=mgr, json={"mode": "SET", "quantity": 205, "reason": "Kiểm kê"})
    client.post(f"{M}/papers/{p['id']}/stock", headers=mgr, json={"mode": "SET", "quantity": 205, "reason": "Không đổi"})
    for kind, iid in (("PAPER", p["id"]), ("PEN", pen["id"]), ("INK", ink["id"])):
        assert _ledger_sum(kind, iid) == _stock(kind, iid), kind
    kinds = [m["kind"] for m in client.get(f"{M}/stock/movements", headers=mgr,
                                           params={"item_kind": "PAPER", "item_id": p["id"]}).json()["items"]]
    assert kinds == ["ADJUST", "RECEIPT", "ADJUST"]              # newest first; the unchanged count wrote nothing
    page = client.get(f"{M}/stock/movements", headers=mgr, params={"kind": "RECEIPT", "page_size": 5}).json()
    assert page["items"][0]["receipt_code"] and page["items"][0]["actor_name"] and page["total"] >= 3


def test_receipt_rejects_bad_lines_and_changes_nothing(client, mgr):
    p = _paper(client, mgr, stock_qty=10)
    line = {"item_kind": "PAPER", "item_id": p["id"], "quantity": 5}
    r = client.post(f"{M}/stock/receipts", headers=mgr, json={"lines": [line, line]})
    assert r.status_code == 422 and _err(r) == "DUPLICATE_LINE"
    r = client.post(f"{M}/stock/receipts", headers=mgr, json={"lines": [line, {**line, "item_id": 999999999}]})
    assert r.status_code == 404 and _err(r) == "ITEM_NOT_FOUND"
    for bad in ({"lines": []}, {"lines": [{**line, "quantity": 0}]}, {"lines": [{**line, "quantity": -3}]},
                {"lines": [{**line, "item_kind": "GLUE"}]}, {"lines": [line], "client_ref": "short"}):
        assert client.post(f"{M}/stock/receipts", headers=mgr, json=bad).status_code == 422, bad
    assert _stock("PAPER", p["id"]) == 10 and _ledger_sum("PAPER", p["id"]) == 10      # the 404 rolled the first line back


def test_the_same_receipt_sent_twice_or_alongside_is_saved_once(client, mgr):
    p = _paper(client, mgr, stock_qty=0)
    ref = _ref()
    body = {"client_ref": ref, "lines": [{"item_kind": "PAPER", "item_id": p["id"], "quantity": 50}]}
    first = client.post(f"{M}/stock/receipts", headers=mgr, json=body)
    again = client.post(f"{M}/stock/receipts", headers=mgr, json=body)
    assert first.status_code == 201 and again.status_code == 200 and again.json()["created"] is False
    assert again.json()["id"] == first.json()["id"] and _stock("PAPER", p["id"]) == 50

    ref2 = _ref()

    def send(_):
        with TestClient(app) as c:
            return c.post(f"{M}/stock/receipts", headers=mgr, json={**body, "client_ref": ref2}).status_code

    with ThreadPoolExecutor(4) as ex:
        codes = sorted(ex.map(send, range(4)))
    assert codes.count(201) == 1 and set(codes) <= {200, 201}, codes
    assert _sql("select count(*) from stock_receipts where client_ref=:r", r=ref2) == 1
    assert _stock("PAPER", p["id"]) == 100 == _ledger_sum("PAPER", p["id"])


def test_receipts_running_alongside_on_the_same_items_all_count(client, mgr):
    a, b = _paper(client, mgr, stock_qty=0), _paper(client, mgr, stock_qty=0)

    def send(i):
        lines = [{"item_kind": "PAPER", "item_id": a["id"], "quantity": 1},
                 {"item_kind": "PAPER", "item_id": b["id"], "quantity": 2}]
        with TestClient(app) as c:   # half the requests list the items the other way round: no deadlock (sorted locks)
            return c.post(f"{M}/stock/receipts", headers=mgr,
                          json={"client_ref": _ref(), "lines": lines if i % 2 else lines[::-1]}).status_code

    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(send, range(6)))
    assert codes == [201] * 6, codes
    assert (_stock("PAPER", a["id"]), _stock("PAPER", b["id"])) == (6, 12)
    assert _ledger_sum("PAPER", a["id"]) == 6 and _ledger_sum("PAPER", b["id"]) == 12


# ---- overview: minimum level and paper kept for scheduled jobs ---------------------------------------
def test_overview_flags_low_and_short_items(client, mgr, cust, staff, wcat, robot, tech):
    p = _paper(client, mgr, stock_qty=10)
    assert p["min_qty"] == 10
    row = _overview_row(client, mgr, "PAPER", p["id"])
    assert (row["status"], row["unit"], row["kept_for_jobs"], row["free"]) == ("OK", "tờ", 0, 10)
    r = client.patch(f"{M}/papers/{p['id']}", headers=mgr, json={"min_qty": 50})
    assert r.status_code == 200 and r.json()["min_qty"] == 50
    assert _overview_row(client, mgr, "PAPER", p["id"])["status"] == "LOW"
    assert client.patch(f"{M}/papers/{p['id']}", headers=mgr, json={"min_qty": -1}).status_code == 422
    pen = _pen(client, mgr, stock_qty=3, min_qty=5)
    assert pen["min_qty"] == 5 and _overview_row(client, mgr, "PEN", pen["id"])["unit"] == "cây"

    # a scheduled job keeps at least one sheet per copy until its paper is taken
    _sql("update paper_types set stock_qty=1 where id=:i returning 1", i=wcat["paper"])
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=3)
    row = _overview_row(client, mgr, "PAPER", wcat["paper"])
    assert row["kept_for_jobs"] >= 3 and row["status"] == "SHORT" and row["free"] < 0


# ---- the technician takes materials ------------------------------------------------------------------
def test_prepare_waits_for_the_paper_and_issue_refuses_short_stock(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=2)
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    st = client.get(f"{T}/jobs/{jid}/stock", headers=tech[0]).json()
    paper = st["lines"][0]
    assert st["issued"] is False and st["can_issue"] is True and paper["item_kind"] == "PAPER" and paper["need"] >= 2
    assert {ln["item_kind"]: ln["need"] for ln in st["lines"]} == {"PAPER": paper["need"], "PEN": 0, "INK": 0}
    r = _post(client, tech, jid, "prepare", status=409)
    assert _err(r) == "STOCK_NOT_ISSUED"

    _sql("update paper_types set stock_qty=:n where id=:i returning 1", n=paper["need"] - 1, i=wcat["paper"])
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": paper["need"], "seen_issued": 0})
    assert r.status_code == 409 and _err(r) == "STOCK_SHORT" and r.json()["error"]["details"]["stock"] == paper["need"] - 1
    assert _stock("PAPER", wcat["paper"]) == paper["need"] - 1                     # nothing taken
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": 0, "new_pen": False, "seen_issued": 0})
    assert r.status_code == 422 and _err(r) == "NOTHING_TO_ISSUE"
    other = _user(client, "TECHNICAL_STAFF")
    assert client.get(f"{T}/jobs/{jid}/stock", headers=other[0]).status_code == 404
    assert client.post(f"{T}/jobs/{jid}/stock/issue", headers=other[0], json={"paper": 1, "seen_issued": 0}).status_code == 404

    # half now, the rest later: Prepare opens only once the need is covered
    _sql("update paper_types set stock_qty=100 where id=:i returning 1", i=wcat["paper"])
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": 1, "seen_issued": 0})
    assert r.status_code == 200 and r.json()["issued"] is (paper["need"] <= 1)
    if paper["need"] > 1:
        _post(client, tech, jid, "prepare", status=409)
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": paper["need"] - 1, "seen_issued": 1})
    assert r.status_code == 200 and r.json()["issued"] is True
    assert _stock("PAPER", wcat["paper"]) == 100 - paper["need"]
    _post(client, tech, jid, "prepare", status=200)
    mv = r.json()["movements"]
    assert {m["kind"] for m in mv} == {"ISSUE"} and sum(m["quantity"] for m in mv) == -paper["need"]
    assert mv[0]["actor_name"] and mv[0]["unit"] == "tờ"


def test_a_double_submitted_issue_takes_stock_once(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=1)
    _sql("update paper_types set stock_qty=100 where id=:i returning 1", i=wcat["paper"])
    need = client.get(f"{T}/jobs/{jid}/stock", headers=tech[0]).json()["lines"][0]["need"]

    def issue(_):
        with TestClient(app) as c:
            return c.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0],
                          json={"paper": need, "new_pen": False, "seen_issued": 0}).status_code

    with ThreadPoolExecutor(4) as ex:
        codes = sorted(ex.map(issue, range(4)))
    assert codes == [200, 409, 409, 409], codes
    assert _stock("PAPER", wcat["paper"]) == 100 - need
    assert _sql("select count(*) from stock_movements where job_id=:j", j=jid) == 1


def test_a_new_pen_takes_one_pen_and_one_ink(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=1)
    pen0, ink0 = _stock("PEN", wcat["gel"]), _stock("INK", wcat["gel_ink"])
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": 0, "new_pen": True, "seen_issued": 0})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["issued"] is False                                                  # a pen alone does not open Prepare
    assert (_stock("PEN", wcat["gel"]), _stock("INK", wcat["gel_ink"])) == (pen0 - 1, ink0 - 1)
    lines = {ln["item_kind"]: ln for ln in st["lines"]}
    assert lines["PEN"]["issued"] == 1 and lines["INK"]["issued"] == 1 and lines["PEN"]["unit"] == "cây"
    _sql("update pen_types set stock_qty=0 where id=:i returning 1", i=wcat["gel"])
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": 0, "new_pen": True, "seen_issued": 0})
    assert r.status_code == 409 and _err(r) == "STOCK_SHORT"
    assert _stock("INK", wcat["gel_ink"]) == ink0 - 1                            # the ink line rolled back with the pen
    _sql("update pen_types set stock_qty=:n where id=:i returning 1", n=pen0, i=wcat["gel"])


def test_finish_returns_unused_paper_and_records_waste(client, cust, staff, mgr, wcat, robot, tech):
    _sql("update paper_types set stock_qty=500 where id=:i returning 1", i=wcat["paper"])
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, qty=1)
    st = client.get(f"{T}/jobs/{jid}/stock", headers=tech[0]).json()
    need, taken = st["lines"][0]["need"], st["lines"][0]["issued"]
    assert taken == need
    issue_paper(client, tech[0], jid, spare=4)                                  # 4 more sheets while running
    before = _stock("PAPER", wcat["paper"])
    r = client.post(f"{T}/jobs/{jid}/finish", headers=tech[0], json={"waste": 1})
    assert r.status_code == 200, r.text
    assert _stock("PAPER", wcat["paper"]) == before + 3                          # 4 spare - 1 spoiled
    paper = _sql("select payload->'stock'->'paper' from job_events where job_id=:j and event_type='WRITTEN'", j=jid)
    assert (paper["used"], paper["waste"], paper["taken"], paper["returned"], paper["extra"]) == (need, 1, need + 4, 3, 0)
    # a finished job takes nothing more
    r = client.post(f"{T}/jobs/{jid}/stock/issue", headers=tech[0], json={"paper": 1, "seen_issued": need + 1})
    assert r.status_code in (409, 422), r.text
    assert client.post(f"{T}/jobs/{jid}/finish", headers=tech[0], json={"waste": -1}).status_code == 422

