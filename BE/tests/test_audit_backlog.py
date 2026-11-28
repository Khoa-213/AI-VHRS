"""Open items of the 2026-11 audit closed on 2026-11-28 (docs/audit/09_APPROVAL_AND_IMPLEMENTATION_PLAN.md, section 12).

TP-06  a Manager takes a started job over when its technician cannot go on
TP-08  one job at a time on a robot; a workstation that goes silent during a run is noticed on the clock
SD-06  a paid order whose production package could not be locked is reported to the Managers
SD-07  the sketch's paper size is checked against the paper being quoted
SD-09  who claimed an order is recorded; the Staff an order is assigned to is told
K2     (not a defect) the database keeps a paid order from being without a paper
K3     paper kept for a scheduled job counts the pages of its document, not one sheet per copy
D09    the rewrite limit says there is no second rewrite
SD-03  "read" in a chat means the other side read it; a Staff who has not claimed the order does not mark anything
SD-08  the Staff queue is filtered and counted by the server (the endpoint the web was already calling)
CO-06  the delivery quote carries the workshop's opening hours, so the web stops copying them
SR-04  a view ticket stops working when its account is locked
SR-05  an agent key opens only the calls the Robot Agent makes
SR-08  the public preview image is rate limited

Real database and triggers.
"""
import pytest

from app.core.config import get_settings
from app.domain import photo_rules as pr
from app.services import background_jobs as bj
from tests.test_api_orders import API, _sql, issue_paper
from tests.test_api_payments import _approved, _deposit, _paid
from tests.test_api_robot_link import fresh_hub  # noqa: F401
from tests.test_api_robot_ops import open_run
from tests.test_api_scheduling import _at, _sched, mgr, robot, tech  # noqa: F401
from tests.test_api_technician import T, _err, _post, _ready, _running, _status
from tests.test_api_workshop import W, _accepted, _user, cust, manager, policy, staff, store, wcat  # noqa: F401
from tests.test_background_jobs import _factory

M = f"{API}/manager"


def _prod(oid):
    return _sql("select production_status::text from orders where id=:o", o=oid)


def _notes(account_id, oid):
    return _sql("select coalesce(string_agg(title, ' | ' order by id), '') from notifications where account_id=:a and order_id=:o "
                "and channel='IN_APP'", a=account_id, o=oid)


# ---------------------------------------------------------------------------------------------- TP-06
def test_a_manager_takes_over_a_started_job(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    url = f"{M}/jobs/{jid}/fail"
    assert client.post(url, headers=tech[0], json={"reason": "Tôi muốn tự đánh hỏng job"}).status_code == 403
    assert client.post(url, headers=mgr, json={"reason": "ngắn"}).status_code == 422
    r = client.post(url, headers=mgr, json={"reason": "Kỹ thuật viên nghỉ ốm, chuyển job cho người khác"})
    assert r.status_code == 201, r.text
    manager_id = client.get(f"{API}/me", headers=mgr).json()["id"]
    assert r.json()["reported_by"] == manager_id and "Quản lý tiếp quản" in r.json()["description"]
    assert _status(jid) == "FAILED" and _prod(oid) == "FAILED"                       # back in the Manager's queue
    assert _sql("select count(*) from audit_logs where action='JOB_FAIL_BY_MANAGER' and entity_id=:j", j=jid) == 1
    again = client.post(url, headers=mgr, json={"reason": "Bấm thêm lần nữa cho chắc"})
    assert again.status_code == 409                                                  # already over

    other = _user(client, "TECHNICAL_STAFF")                                         # somebody else can now be given the order
    from tests.test_api_scheduling import _robot
    replan = _sched(client, mgr, oid, _robot(), other[1], _at(3, 9))
    assert replan.status_code == 201, replan.text


def test_a_job_that_was_not_started_is_replanned_not_failed(client, cust, staff, mgr, wcat, robot, tech):
    from tests.test_api_technician import _job
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech)
    r = client.post(f"{M}/jobs/{jid}/fail", headers=mgr, json={"reason": "Job chưa bắt đầu thì dùng đổi lịch"})
    assert r.status_code == 409 and _status(jid) == "SCHEDULED"
    assert client.post(f"{M}/jobs/999999999/fail", headers=mgr, json={"reason": "Job không tồn tại đâu cả"}).status_code == 404


# ---------------------------------------------------------------------------------------------- TP-08
def test_a_robot_prepares_one_job_at_a_time(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)                 # job 1 is writing on the robot
    oid2, _, _ = _paid(client, cust, staff[0], wcat)
    second = _sched(client, mgr, oid2, robot, tech[1], _at(2, 9))
    assert second.status_code == 201, second.text
    jid2 = second.json()["id"]
    assert client.get(f"{T}/jobs/{jid2}/package", headers=tech[0]).status_code == 200
    issue_paper(client, tech[0], jid2)
    r = _post(client, tech, jid2, "prepare")
    assert r.status_code == 409 and _err(r) == "ROBOT_HAS_ACTIVE_JOB" and r.json()["error"]["details"] == {"job_id": jid}, r.text
    assert _post(client, tech, jid, "incidents", {"type": "OTHER", "description": "Dừng job một để nhường robot"}).status_code == 201
    assert _post(client, tech, jid2, "prepare").status_code == 200                   # the robot is free again


def test_a_silent_workstation_during_a_run_is_noticed_on_the_clock(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    with _factory()() as s:
        assert bj.JOBS["robot_watch"](s, order_ids=[oid]) == {"skipped": True}       # a scoped run of other jobs does not sweep
    assert _sql("select count(*) from robot_alerts where robot_id=:r", r=robot) == 0
    _sql("update robots set last_seen_at = now() - interval '10 minutes' where id=:r returning 1", r=robot)
    with _factory()() as s:
        out = bj.JOBS["robot_watch"](s)
    assert out["alerts_raised"] >= 2                                                 # nobody opened a robot screen
    codes = _sql("select string_agg(code, ',' order by code) from robot_alerts where robot_id=:r and resolved_at is null", r=robot)
    assert codes == "AGENT_OFFLINE,RUN_OUTCOME_UNKNOWN"
    with _factory()() as s:
        bj.JOBS["robot_watch"](s)
    assert _sql("select count(*) from robot_alerts where robot_id=:r", r=robot) == 2 # the same alerts are not raised twice


# ---------------------------------------------------------------------------------------------- SD-06
def test_a_paid_order_that_cannot_be_locked_is_reported_to_the_managers(client, cust, staff, manager, wcat, monkeypatch):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    monkeypatch.setattr(get_settings(), "production_signing_key", None)             # the package cannot be signed
    r = client.post(f"{API}/payments/{p['id']}/mock-checkout", headers=cust, json={"result": "SUCCESS"})
    assert r.status_code == 200 and r.json()["order_status"] == "CONFIRMED", r.text   # the payment itself still stands
    assert _sql("select count(*) from production_snapshots where order_id=:o", o=oid) == 0
    why = _sql("select new_value->>'reason' from audit_logs where action='PRODUCTION_SNAPSHOT_FAILED' and entity_id=:o", o=oid)
    assert why == "PRODUCTION_SIGNING_NOT_CONFIGURED"
    assert "chưa khoá được gói sản xuất" in _notes(manager[1], oid)
    assert _sql("select msg_code from notifications where account_id=:a and order_id=:o order by id desc limit 1",
                a=manager[1], o=oid) == "SNAP_FAIL"


# ---------------------------------------------------------------------------------------------- SD-07
def test_a_quotation_is_not_sent_for_a_sketch_laid_out_on_another_paper_size(client, cust, staff, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    paper = _sql("select size::text from paper_types where id=:i", i=wcat["paper"])
    other = "A4" if paper != "A4" else "A5"
    wrong = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={"paper_size": other})
    assert wrong.status_code == 201, wrong.text
    assert client.post(f"{W}/orders/{oid}/sketches/{wrong.json()['version']}/finalize", headers=sh).status_code == 200
    q = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert q.status_code == 201, q.text
    r = client.post(f"{W}/quotations/{q.json()['id']}/send", headers=sh)
    assert r.status_code == 409 and _err(r) == "PAPER_SIZE_MISMATCH", r.text
    assert r.json()["error"]["details"]["sketch"] == [other] and r.json()["error"]["details"]["papers"][0]["size"] == paper

    assert client.post(f"{W}/quotations/{q.json()['id']}/cancel", headers=sh).status_code == 200
    right = client.post(f"{W}/orders/{oid}/sketches/generate", headers=sh, json={})          # the order's own paper size
    assert client.post(f"{W}/orders/{oid}/sketches/{right.json()['version']}/finalize", headers=sh).status_code == 200
    q2 = client.post(f"{W}/orders/{oid}/quotations", headers=sh, json={})
    assert client.post(f"{W}/quotations/{q2.json()['id']}/send", headers=sh).status_code == 200


# ---------------------------------------------------------------------------------------------- SD-09
def test_claiming_is_recorded_and_an_assignment_tells_the_staff(client, cust, staff, manager, wcat):
    from tests.test_api_workshop import _ot3
    oid = _ot3(client, cust, wcat)                                                   # submitted, nobody's yet
    assert client.post(f"{W}/orders/{oid}/claim", headers=staff[0]).status_code == 200
    assert _sql("select actor_id from audit_logs where action='ORDER_CLAIM' and entity_id=:o", o=oid) == staff[1]
    assert client.post(f"{W}/orders/{oid}/claim", headers=staff[0]).status_code == 200            # again: nothing new
    assert _sql("select count(*) from audit_logs where action='ORDER_CLAIM' and entity_id=:o", o=oid) == 1

    other = _user(client, "STAFF")
    assert client.put(f"{M}/orders/{oid}/assignment", headers=manager[0], json={"staff_id": other[1]}).status_code == 200
    assert "Bạn được giao đơn" in _notes(other[1], oid)
    assert client.put(f"{M}/orders/{oid}/assignment", headers=manager[0], json={"staff_id": other[1]}).status_code == 200
    assert _notes(other[1], oid).count("Bạn được giao đơn") == 1                     # the same assignment again says nothing


# ---------------------------------------------------------------------------------------------- K2
def test_the_database_itself_keeps_a_paid_order_from_losing_its_paper(client, cust, staff, wcat):
    """K2 of the stock audit said an order without a paper could reach production and bypass the ledger. It cannot: the
    database refuses it (chk_orders_materials_after_submit), so no application check was added."""
    from sqlalchemy.exc import IntegrityError
    oid, _, _ = _paid(client, cust, staff[0], wcat)
    with pytest.raises(IntegrityError) as e:
        _sql("update orders set paper_type_id = null where id=:o returning 1", o=oid)
    assert "chk_orders_materials_after_submit" in str(e.value)


# ---------------------------------------------------------------------------------------------- D09
def test_the_rewrite_limit_says_there_is_no_second_rewrite():
    pr.check_rewrite_allowed(False)
    with pytest.raises(pr.PhotoRuleError) as e:
        pr.check_rewrite_allowed(True)
    assert e.value.code == "REWRITE_LIMIT_REACHED"
    assert "không viết lại thêm" in str(e.value) and "báo giá viết lại" not in str(e.value)


# ---------------------------------------------------------------------------------------------- SR-05
def test_an_agent_key_opens_only_what_the_agent_calls(client, cust, staff, mgr, wcat, robot, tech):
    from tests.conftest import agent_h
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    ah = agent_h(jid)
    assert client.get(f"{T}/jobs/{jid}", headers=ah).status_code == 200              # what the agent does: read its job,
    assert client.get(f"{T}/jobs/{jid}/package", headers=ah).status_code == 200      # fetch the package,
    r, run = open_run(client, tech, jid)                                             # open a run (the helper plays the agent)
    assert r.status_code == 201, r.text
    for method, path, body in (                                                      # what only a person does
            ("post", f"jobs/{jid}/finish", {}),
            ("post", f"jobs/{jid}/incidents", {"type": "OTHER", "description": "Khoá agent bị lộ thử báo sự cố"}),
            ("post", f"jobs/{jid}/photos/submit", {}),
            ("post", f"jobs/{jid}/qc-fail", {"reason": "Khoá agent bị lộ thử đánh hỏng bài"}),
            ("get", "jobs", None),
            ("post", f"jobs/{jid}/stock/issue", {}),
            ("post", f"robots/{robot}/view-ticket", None)):
        got = getattr(client, method)(f"{T}/{path}", headers=ah, **({"json": body} if body is not None else {}))
        assert got.status_code == 403 and _err(got) == "AGENT_ROUTE_NOT_ALLOWED", (path, got.text)
    assert _status(jid) == "WRITING"                                                 # nothing happened to the job


# ---------------------------------------------------------------------------------------------- SR-04
def test_a_view_ticket_dies_with_its_account(client, cust, staff, mgr, wcat, robot, tech):
    from tests.test_api_technician import _job
    _job(client, cust, staff, mgr, wcat, robot, tech)
    t = client.post(f"{T}/robots/{robot}/view-ticket", headers=tech[0]).json()["ticket"]
    assert client.get(f"{API}/viewer/{t}/live").status_code == 200
    _sql("update accounts set status='LOCKED' where id=:a returning 1", a=tech[1])
    for what in ("live", "scene"):
        r = client.get(f"{API}/viewer/{t}/{what}")
        assert r.status_code == 401 and _err(r) == "INVALID_VIEW_TICKET", r.text
    _sql("update accounts set status='ACTIVE' where id=:a returning 1", a=tech[1])
    assert client.get(f"{API}/viewer/{t}/live").status_code == 200                   # unlocked again: the same ticket works


# ---------------------------------------------------------------------------------------------- SR-08
def test_the_public_preview_image_is_rate_limited(client, wcat):
    from app.core.ratelimit import limiter
    url = f"{API}/catalog/templates/{wcat['tpl']}/preview"
    assert client.get(url).status_code == 200
    for _ in range(599):                                   # the test client has no literal IP, so its key is "unknown"
        assert limiter.hit("template_preview_get", "unknown", 600, 60) == 0
    r = client.get(url)
    assert r.status_code == 429 and _err(r) == "RATE_LIMITED"


# ---------------------------------------------------------------------------------------------- SD-03
def test_read_in_a_chat_means_the_other_side_read_it(client, cust, staff, manager, wcat):
    sh, _ = staff
    oid = _accepted(client, cust, sh, wcat)
    url = f"{API}/orders/{oid}/messages"
    assert client.post(url, headers=cust, json={"body": "Chào xưởng"}).status_code == 201
    assert client.post(url, headers=sh, json={"body": "Chào bạn, đơn đã nhận"}).status_code == 201
    assert client.get(url, headers=manager[0]).json()["unread"] == 1                 # only what the customer wrote
    assert client.post(f"{url}/read", headers=manager[0]).json() == {"marked": 1}
    seen = {m["body"]: m["read_at"] for m in client.get(url, headers=sh).json()["items"]}
    assert seen["Chào xưởng"] is not None
    assert seen["Chào bạn, đơn đã nhận"] is None                                     # the customer has not read the Staff's message
    assert client.get(url, headers=cust).json()["unread"] == 1
    assert client.post(f"{url}/read", headers=cust).json() == {"marked": 1}
    assert client.get(f"{API}/workshop/conversations/unread-count", headers=manager[0]).status_code == 200


def test_a_staff_who_has_not_claimed_the_order_marks_nothing_read(client, cust, staff, wcat):
    from tests.test_api_workshop import _ot3
    sh, _ = staff
    oid = _ot3(client, cust, wcat)                                                   # in the pool
    url = f"{API}/orders/{oid}/messages"
    assert client.post(url, headers=cust, json={"body": "Có ai nhận đơn chưa ạ"}).status_code == 201
    assert client.get(url, headers=sh).json()["unread"] == 1
    assert client.post(f"{url}/read", headers=sh).json() == {"marked": 0}            # only looking
    assert client.post(f"{W}/orders/{oid}/claim", headers=sh).status_code == 200
    assert client.get(url, headers=sh).json()["unread"] == 1                         # still unread for the Staff now in charge
    assert client.post(f"{url}/read", headers=sh).json() == {"marked": 1}


# ---------------------------------------------------------------------------------------------- SD-08
def test_the_staff_queue_is_filtered_and_counted_by_the_server(client, cust, staff, manager, wcat):
    from tests.test_api_workshop import _ot3
    sh, sid = staff
    other = _user(client, "STAFF")
    counts = lambda h: client.get(f"{W}/queue-counts", headers=h).json()             # noqa: E731
    ids = lambda h, **q: [o["id"] for o in client.get(f"{W}/orders", headers=h, params={"page_size": 100, **q}).json()["items"]]  # noqa: E731
    pool_before = counts(sh)["pool"]
    assert counts(sh)["mine"] == {}
    mine = _accepted(client, cust, sh, wcat)
    pooled = _ot3(client, cust, wcat)
    theirs = _accepted(client, cust, other[0], wcat)

    assert counts(sh) == {"pool": pool_before + 1, "mine": {"ACCEPTED": 1}}
    assert counts(manager[0]) == {"pool": pool_before + 1, "mine": {}}               # a Manager holds no order of their own
    assert client.get(f"{W}/queue-counts", headers=cust).status_code == 403

    assert ids(sh, mine="true") == [mine]
    assert ids(manager[0], mine="true") == []
    assert ids(sh, order_ids=[mine, pooled, theirs]) == [mine, pooled]               # never another Staff's order
    assert ids(manager[0], order_ids=[mine, pooled, theirs]) == [mine, pooled, theirs]
    code = _sql("select code from orders where id=:o", o=mine)
    assert ids(sh, q=code.lower(), mine="true") == [mine]
    _sql("update accounts set full_name='Trần Thị Hàng Đợi' where id=(select customer_id from orders where id=:o) returning 1", o=mine)
    # by the customer's name too. Typed as stored: whether "đ" finds "Đ" follows the database's locale (the throwaway test
    # database is "C" and does not fold letters outside ASCII; a UTF-8 locale does)
    assert ids(sh, q="Hàng Đợi") == [mine, pooled]
    assert ids(sh, q="Hàng Đợi", unassigned="true") == [pooled]


# ---------------------------------------------------------------------------------------------- CO-06
def test_the_delivery_quote_carries_the_opening_hours(client, cust, staff, mgr, wcat, robot, tech, store, monkeypatch):
    from app.core.errors import AppError
    from app.services.delivery import DeliveryService
    from tests.test_api_delivery_final import _final_stage
    from tests.test_api_scheduling import CAL
    oid = _final_stage(client, cust, staff, mgr, wcat, robot, tech, store)
    url = f"{API}/orders/{oid}/delivery-quote"
    hours = client.get(url, headers=cust).json()["pickup_hours"]
    assert hours == {"days": sorted(CAL.days), "start": CAL.start.strftime("%H:%M"), "end": CAL.end.strftime("%H:%M"),
                     "utc_offset_min": int(CAL.tz.utcoffset(None).total_seconds() // 60)}

    def broken(self):
        raise AppError(503, "WORKING_HOURS_INVALID", "x")
    monkeypatch.setattr(DeliveryService, "_calendar", broken)
    r = client.get(url, headers=cust)
    assert r.status_code == 200 and r.json()["pickup_hours"] is None                 # the prices are still quoted


# ---------------------------------------------------------------------------------------------- K3
def test_paper_kept_for_a_scheduled_job_counts_its_pages(client, cust, staff, mgr, wcat, robot, tech):
    from tests.test_api_stock import _overview_row
    from tests.test_api_technician import _job
    kept = lambda: _overview_row(client, mgr, "PAPER", wcat["paper"])["kept_for_jobs"]          # noqa: E731
    before = kept()
    oid, jid = _job(client, cust, staff, mgr, wcat, robot, tech, qty=2)
    sketch = _sql("select sketch_id from production_jobs where id=:j", j=jid)
    pages = _sql("select greatest(coalesce(cardinality(image_urls), 0), 1) from sketches where id=:s", s=sketch)
    assert kept() == before + 2 * pages
    _sql("update sketches set image_urls = array['a.jpg','b.jpg','c.jpg'] where id=:s returning 1", s=sketch)   # three pages
    assert kept() == before + 2 * 3
    _sql("update sketches set image_urls = '{}' where id=:s returning 1", s=sketch)             # an old sketch: one page
    assert kept() == before + 2
    assert client.get(f"{T}/jobs/{jid}/package", headers=tech[0]).status_code == 200
    issue_paper(client, tech[0], jid)                                                           # taken: no longer "kept"
    assert kept() == before
