"""Cross-check of the two audits, 2026-11-28 (docs/audit/09_APPROVAL_AND_IMPLEMENTATION_PLAN.md, section 7).

A01  a run ends DONE only with every stroke of its plan
A02  "written" needs one finished robot run per copy of the order (the agent writes one copy per run)
L2   a robot run is opened and closed by the robot's own agent key, never by a person's login; the agent can still report
     how its run ended after the job left its live states
L1   on a real robot only a REAL run is a written copy; a SIM or MOCK run that ended DONE is not (a robot marked simulated
     keeps counting every finished run)
A05  a command the agent pulled but never answered: a halt is handed out again, anything else is never repeated, and after
     the wait the command says NO_ANSWER instead of staying DELIVERED for ever
A03  a REAL writing run needs the server's own validation of the trajectory (not the workstation's word), whatever
     MOTION_VALIDATION_REQUIRED says; A08: and a signed production package
A06  a run the agent could not close: the technician or a Manager closes it as UNKNOWN with a reason, the Manager's
     "written" override gets past it, and the agent's own late report replaces the UNKNOWN
D03  (1a) the real arm is put in motion from its workstation only: a REAL RUN / DRY_RUN / ALIGN_START, and RESUME or
     PAPER_CHANGED of a REAL run, are accepted only from the login session of the app that started the connected agent
A07  money reported after a failed report: the order that still waits for exactly that payment is confirmed, anything
     else is flagged for the refund flow

Real database and triggers. The agent is simulated by the test; no robot is involved.
"""
from app.services.robot_link import hub
from tests.test_api_orders import API, _sql
from tests.test_api_payments import _approved, _code, _deposit, _hook, _signed
from tests.conftest import agent_h, login, make_account
from tests.test_api_robot_link import A, bearer, fresh_hub, key_for, session_key, sync  # noqa: F401
from tests.test_api_robot_ops import open_run
from tests.test_api_scheduling import mgr, robot, tech  # noqa: F401
from tests.test_api_technician import CAL_MOTION, T, _err, _post, _robot_wrote, _running, _status
from tests.test_api_workshop import cust, policy, staff, store, wcat  # noqa: F401

M = f"{API}/manager"
WHY = "Robot đã dừng, máy trạm mất mạng lúc viết xong"


def _close(client, tech, run, result, done, total=10):
    return client.patch(f"{T}/runs/{run}", headers=agent_h(run=run), json={"result": result, "completed_strokes": done, "total_strokes": total})


def _cmd(client, who, jid, kind, key=None, **params):
    body = {"kind": kind, "job_id": jid, "params": params, **({"idempotency_key": key} if key else {})}
    return client.post(f"{T}/robot-commands", headers=who[0], json=body)


def _age(command_id, seconds, column):
    _sql(f"update robot_commands set {column} = now() - make_interval(secs => :s) where id=:c returning 1", s=seconds, c=command_id)


def _quiet(robot_id, seconds=300):
    """The robot's workstation has not been heard from for this long (the hub does not see it either)."""
    _sql("update robots set last_seen_at = now() - make_interval(secs => :s) where id=:r returning 1", s=seconds, r=robot_id)


def _command(client, tech, command_id):
    return client.get(f"{T}/robot-commands/{command_id}", headers=tech[0]).json()


# ---------------------------------------------------------------------------------------------- A01
def test_a_run_is_done_only_with_every_stroke_of_its_plan(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201, r.text
    part = _close(client, tech, run, "DONE", 3)
    assert part.status_code == 422 and _err(part) == "RESULT_INVALID" and part.json()["error"]["details"] == {"completed": 3, "total": 10}
    assert _post(client, tech, jid, "finish").status_code == 409                     # still open: nothing was written off
    assert _close(client, tech, run, "STOPPED", 3).status_code == 200                # what a part-written run really is
    r = _post(client, tech, jid, "finish")
    assert r.status_code == 409 and _err(r) == "RUN_EVIDENCE_REQUIRED"


# ---------------------------------------------------------------------------------------------- A02
def test_written_needs_one_finished_run_for_each_copy(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, qty=3)
    detail = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()
    assert detail["quantity"] == 3 and detail["copies_written"] == 0 and detail["open_run"] is None

    _robot_wrote(client, tech, jid)
    r = _post(client, tech, jid, "finish")
    assert r.status_code == 409 and _err(r) == "COPIES_MISSING", r.text
    assert r.json()["error"]["details"] == {"written": 1, "quantity": 3, "simulated_runs_not_counted": 0}
    assert _status(jid) == "WRITING"
    _robot_wrote(client, tech, jid)
    assert client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["copies_written"] == 2
    assert _err(_post(client, tech, jid, "finish")) == "COPIES_MISSING"
    _robot_wrote(client, tech, jid)
    r = _post(client, tech, jid, "finish")
    assert r.status_code == 200 and _status(jid) == "WRITTEN", r.text
    written = _sql("select new_value from audit_logs where action='JOB_WRITTEN' and entity_id=:j order by id desc limit 1", j=jid)
    assert written["copies_written"] == 3 and written["quantity"] == 3


def test_a_manager_may_record_written_with_fewer_reported_copies(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, qty=2)
    _robot_wrote(client, tech, jid)
    assert _err(_post(client, tech, jid, "finish")) == "COPIES_MISSING"
    r = client.post(f"{M}/jobs/{jid}/finish-override", headers=mgr, json={"reason": "Bản thứ hai viết khi máy trạm mất mạng, đã kiểm tra tờ giấy"})
    assert r.status_code == 200 and _status(jid) == "WRITTEN", r.text
    over = _sql("select new_value from audit_logs where action='JOB_FINISH_OVERRIDE' and entity_id=:j order by id desc limit 1", j=jid)
    assert over["copies_written"] == 1 and over["quantity"] == 2


# ---------------------------------------------------------------------------------------------- A06
def test_the_technician_closes_a_run_the_agent_left_open_and_works_on(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    info = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["open_run"]
    assert info["run_id"] == run and info["orphan"] is False                        # heard from a moment ago (the run was just opened)
    early = client.post(f"{T}/runs/{run}/close-orphan", headers=tech[0], json={"reason": WHY})
    assert early.status_code == 409 and _err(early) == "RUN_STILL_ACTIVE"            # a server restart must not make every run look abandoned
    _quiet(robot)
    info = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["open_run"]
    assert info["orphan"] is True                                                   # silent for minutes and not connected: nobody is running it
    blocked = _post(client, tech, jid, "finish")
    assert _err(blocked) == "RUN_OPEN" and blocked.json()["error"]["details"] == {"open_run_id": run, "orphan": True}
    busy, _ = open_run(client, tech, jid)
    assert _err(busy) == "ROBOT_BUSY"

    url = f"{T}/runs/{run}/close-orphan"
    assert client.post(url, headers=tech[0], json={"reason": "ngắn"}).status_code == 422
    r = client.post(url, headers=tech[0], json={"reason": WHY})
    assert r.status_code == 200 and r.json()["result"] == "UNKNOWN" and r.json()["ended_at"], r.text
    assert _sql("select count(*) from audit_logs where action='ROBOT_RUN_CLOSE_ORPHAN' and reason=:w", w=WHY) >= 1
    again = client.post(url, headers=tech[0], json={"reason": WHY})
    assert again.status_code == 409 and _err(again) == "RUN_ALREADY_CLOSED"
    assert client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["open_run"] is None
    nxt, _ = open_run(client, tech, jid)
    assert nxt.status_code == 201                                                    # the robot is free again


def test_a_run_the_agent_is_still_executing_is_not_closed_by_hand(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    sync(client, ah, status={"mode": "SIM", "busy": True})                           # the workstation says: I am running
    assert client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["open_run"]["orphan"] is False
    for who, base in ((tech[0], T), (mgr, M)):
        r = client.post(f"{base}/runs/{run}/close-orphan", headers=who, json={"reason": WHY})
        assert r.status_code == 409 and _err(r) == "RUN_STILL_ACTIVE", r.text
    r = client.post(f"{M}/jobs/{jid}/finish-override", headers=mgr, json={"reason": WHY})
    assert r.status_code == 409 and _err(r) == "RUN_OPEN" and r.json()["error"]["details"]["orphan"] is False

    sync(client, ah, status={"mode": "SIM", "busy": False})                          # connected and idle: the close message was lost
    assert client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["open_run"]["orphan"] is True
    r = client.post(f"{M}/runs/{run}/close-orphan", headers=mgr, json={"reason": WHY})
    assert r.status_code == 200 and r.json()["result"] == "UNKNOWN"


def test_the_managers_override_gets_past_an_orphan_run(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    _quiet(robot)
    r = client.post(f"{M}/jobs/{jid}/finish-override", headers=mgr, json={"reason": WHY})
    assert r.status_code == 200 and _status(jid) == "WRITTEN", r.text
    row = _sql("select result || ':' || (summary->>'reason') from robot_runs where run_id=:r", r=run)
    assert row == "UNKNOWN:" + WHY


def test_the_managers_job_detail_shows_copies_and_the_stuck_run(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    """What the Manager's web screen reads before offering "record as written" and "close the stuck run"."""
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, qty=2)
    d = client.get(f"{M}/jobs/{jid}", headers=mgr).json()
    assert d["status"] == "WRITING" and d["quantity"] == 2 and d["copies_written"] == 0 and d["open_run"] is None
    _robot_wrote(client, tech, jid)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    _quiet(robot)
    d = client.get(f"{M}/jobs/{jid}", headers=mgr).json()
    assert d["copies_written"] == 1 and d["open_run"]["run_id"] == run and d["open_run"]["orphan"] is True
    assert client.post(f"{M}/runs/{run}/close-orphan", headers=mgr, json={"reason": WHY}).status_code == 200
    assert client.get(f"{M}/jobs/{jid}", headers=mgr).json()["open_run"] is None


def test_the_agents_late_report_replaces_the_unknown_a_person_recorded(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _sql("update robots set is_simulated = true where id=:r returning 1", r=robot)       # a simulated robot: its finished run is the copy (L1)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    _quiet(robot)
    assert client.post(f"{T}/runs/{run}/close-orphan", headers=tech[0], json={"reason": WHY}).status_code == 200
    assert _err(_post(client, tech, jid, "finish")) == "RUN_EVIDENCE_REQUIRED"       # UNKNOWN is not a written copy

    late = _close(client, tech, run, "DONE", 10)                                     # the link is back: the agent sends what really happened
    assert late.status_code == 200 and late.json()["result"] == "DONE", late.text
    kept = _sql("select summary from robot_runs where run_id=:r", r=run)
    assert kept["reason"] == WHY and kept["closed_by_person"] == tech[1] and kept["agent_reported_at"]
    assert _sql("select count(*) from audit_logs where action='ROBOT_RUN_LATE_RESULT' and entity_id=(select id from robot_runs where run_id=:r)",
                r=run) == 1
    assert _post(client, tech, jid, "finish").status_code == 200                     # and it counts as the copy it was

    other = _close(client, tech, run, "FAULT", 2)                                    # a normal closed run still cannot be rewritten
    assert other.status_code == 409 and _err(other) == "RUN_ALREADY_CLOSED"


# ---------------------------------------------------------------------------------------------- A05
def test_an_unanswered_stop_is_handed_out_again_and_then_says_no_answer(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    cid = _cmd(client, tech, jid, "STOP").json()["id"]
    assert [c["id"] for c in sync(client, ah)["commands"]] == [cid]
    assert sync(client, ah)["commands"] == []                                        # handed out a moment ago: not yet again
    _age(cid, 5, "delivered_at")
    assert [c["id"] for c in sync(client, ah)["commands"]] == [cid]                  # still no answer: the agent gets it again
    assert _command(client, tech, cid)["status"] == "DELIVERED"

    _age(cid, 120, "created_at")
    _age(cid, 120, "delivered_at")
    assert sync(client, ah)["commands"] == []                                        # the wait is over: not handed out any more
    gone = _command(client, tech, cid)
    assert gone["status"] == "FAILED" and gone["error_code"] == "NO_ANSWER" and "E-Stop" in gone["error_message"]

    # the answer arrives after all: it is kept, not thrown away
    r = client.post(f"{A}/commands/{cid}/result", headers=ah, json={"ok": True, "result": {"stopped": True}})
    assert r.status_code == 200 and r.json()["status"] == "DONE" and r.json()["error_code"] is None, r.text


def test_a_command_that_moves_the_arm_is_never_handed_out_twice(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    cid = _cmd(client, tech, jid, "RUN", mode="SIM").json()["id"]
    assert [c["id"] for c in sync(client, ah)["commands"]] == [cid]
    _age(cid, 30, "delivered_at")
    hub.live(robot).pending = True                                                   # make the next sync look at the table
    assert sync(client, ah)["commands"] == []
    assert _command(client, tech, cid)["status"] == "DELIVERED"                      # a run may take long to answer: still waiting
    _age(cid, 600, "delivered_at")
    hub.live(robot).pending = True
    assert sync(client, ah)["commands"] == []
    assert _command(client, tech, cid)["error_code"] == "NO_ANSWER"


def test_an_idempotency_key_names_one_command_with_its_parameters(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    first = _cmd(client, tech, jid, "RUN", key="click-0001", mode="SIM")
    same = _cmd(client, tech, jid, "RUN", key="click-0001", mode="SIM")
    assert first.status_code == 201 and same.status_code == 201 and same.json()["id"] == first.json()["id"]
    other = _cmd(client, tech, jid, "RUN", key="click-0001", mode="MOCK")
    assert other.status_code == 409 and _err(other) == "IDEMPOTENCY_KEY_REUSED"


# ---------------------------------------------------------------------------------------------- A07
def _report(client, oid, p, result):
    body, sig = _signed(p["gateway_txn_id"], _code(oid), int(float(p["amount"])), result)
    return _hook(client, p["gateway"], body, sig)


def _flag(payment_id):
    return _sql("select gateway_payload->>'needs_refund' from payments where id=:p", p=payment_id)


def _order(oid):
    return _sql("select order_status::text from orders where id=:o", o=oid)


def test_money_reported_after_a_failed_report_confirms_the_order_that_still_waits_for_it(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    p = _deposit(client, cust, oid)
    assert _report(client, oid, p, "FAILED").json()["status"] == "FAILED"
    again = _report(client, oid, p, "FAILED")
    assert again.json()["result"] == "ALREADY_PROCESSED" and _order(oid) == "AWAITING_DEPOSIT"   # a repeated failure is still nothing

    r = _report(client, oid, p, "SUCCESS")
    assert r.status_code == 200 and r.json() == {"result": "PROCESSED", "status": "SUCCESS", "order_status": "CONFIRMED",
                                                 "needs_refund": None}, r.text
    assert _sql("select status::text from payments where id=:p", p=p["id"]) == "SUCCESS" and _flag(p["id"]) is None
    assert _sql("select count(*) from audit_logs where action='PAYMENT_RECOVERED' and entity_id=:p", p=p["id"]) == 1
    assert _sql("select count(*) from production_snapshots where order_id=:o", o=oid) == 1         # locked as with any deposit
    assert _report(client, oid, p, "SUCCESS").json()["result"] == "ALREADY_PROCESSED"              # and only once


def test_money_for_a_failed_payment_the_customer_has_left_behind_is_flagged_for_refund(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    p1 = _deposit(client, cust, oid)
    _report(client, oid, p1, "FAILED")
    p2 = _deposit(client, cust, oid)                                                 # a newer attempt: the order waits for that one
    assert p2["id"] != p1["id"]
    r = _report(client, oid, p1, "SUCCESS")
    assert r.json()["result"] == "PROCESSED" and r.json()["needs_refund"] is True and r.json()["status"] == "FAILED", r.text
    assert _order(oid) == "AWAITING_DEPOSIT" and _flag(p1["id"]) == "true"
    assert _sql("select count(*) from audit_logs where action='PAYMENT_ORPHAN' and entity_id=:p", p=p1["id"]) == 1
    assert _report(client, oid, p1, "SUCCESS").json()["needs_refund"] is True        # repeated: flagged once
    assert _sql("select count(*) from audit_logs where action='PAYMENT_ORPHAN' and entity_id=:p", p=p1["id"]) == 1

    assert _report(client, oid, p2, "SUCCESS").json()["order_status"] == "CONFIRMED"
    assert _flag(p2["id"]) is None


def test_money_for_a_failed_payment_of_an_order_already_paid_is_flagged_for_refund(client, cust, staff, wcat):
    oid, q, _ = _approved(client, cust, staff[0], wcat)
    p1 = _deposit(client, cust, oid)
    _report(client, oid, p1, "FAILED")
    p2 = _deposit(client, cust, oid)
    assert _report(client, oid, p2, "SUCCESS").json()["order_status"] == "CONFIRMED"
    r = _report(client, oid, p1, "SUCCESS")                                          # paid twice in the end
    assert r.json()["needs_refund"] is True and _flag(p1["id"]) == "true" and _order(oid) == "CONFIRMED"


# ---------------------------------------------------------------------------------------------- A03 / A08
def _real(client, tech, jid):
    return open_run(client, tech, jid, mode="REAL", authorized=True, plan_digest="a" * 64)


def test_the_real_robot_does_not_write_on_the_workstations_word_alone(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    from app.core.config import get_settings
    assert get_settings().motion_validation_required is False                        # the default the gate must not depend on
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)                 # calibration without the motion block
    assert _sql("select simulation_report->'server_validation'->>'status' from production_jobs where id=:j", j=jid) == "NOT_RUN"
    r, _ = _real(client, tech, jid)
    assert r.status_code == 409 and _err(r) == "SERVER_VALIDATION_REQUIRED" and r.json()["error"]["details"] == {"server_validation": "NOT_RUN"}
    _, ah = key_for(client, mgr, robot)
    sync(client, ah)
    c = _cmd(client, tech, jid, "RUN", mode="REAL", authorization=f"AUTHORIZE-{jid}-abcd1234")
    assert c.status_code == 409 and _err(c) == "SERVER_VALIDATION_REQUIRED"          # said before the agent is asked to move

    sim, _ = open_run(client, tech, jid)                                             # the simulator and the mock robot are not held back
    assert sim.status_code == 201
    assert _sql("select count(*) from robot_runs where job_id=:j and mode='REAL'", j=jid) == 0


def test_the_real_robot_writes_after_the_servers_own_validation_passed(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, cal=CAL_MOTION)
    assert _sql("select simulation_report->'server_validation'->>'status' from production_jobs where id=:j", j=jid) == "PASS"
    r, _ = _real(client, tech, jid)
    assert r.status_code == 201 and r.json()["mode"] == "REAL", r.text


def test_the_real_robot_does_not_write_a_job_without_a_signed_package(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, cal=CAL_MOTION)
    _sql("update production_jobs set snapshot_id = null where id=:j returning 1", j=jid)   # a job scheduled before packages were signed
    r, _ = _real(client, tech, jid)
    assert r.status_code == 409 and _err(r) == "PACKAGE_NOT_SIGNED", r.text
    rehearsal, _ = open_run(client, tech, jid, mode="SIM")
    assert rehearsal.status_code == 201


# ---------------------------------------------------------------------------------------------- D03 / 1a
def _two_logins(client):
    """One technician signed in twice: at the workstation (the app that starts the agent) and on another computer."""
    email = make_account("TECHNICAL_STAFF")
    here = {"Authorization": f"Bearer {login(client, email)['access_token']}"}
    away = {"Authorization": f"Bearer {login(client, email)['access_token']}"}
    return (here, client.get(f"{API}/me", headers=here).json()["id"]), away


def _real_cmd(client, headers, jid, kind="RUN", **extra):
    return client.post(f"{T}/robot-commands", headers=headers,
                       json={"kind": kind, "job_id": jid, "params": {"mode": "REAL", "authorization": f"AUTHORIZE-{jid}-abcd1234", **extra}})


def test_the_real_robot_is_started_only_from_the_app_at_its_workstation(client, cust, staff, mgr, wcat, robot, fresh_hub):
    tech, away = _two_logins(client)
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, cal=CAL_MOTION)
    key = session_key(client, tech, robot, "workstation-app-01")["key"]          # the app at the workstation starts the agent with it
    assert _sql("select auth_session_id is not null from robot_agents where robot_id=:r and kind='SESSION' order by id desc limit 1", r=robot)
    sync(client, bearer(key))

    for kind in ("RUN", "DRY_RUN", "ALIGN_START"):
        far = _real_cmd(client, away, jid, kind)                                  # same account, another computer
        assert far.status_code == 403 and _err(far) == "REAL_ONLY_AT_WORKSTATION", (kind, far.text)
    assert client.post(f"{T}/robot-commands", headers=away, json={"kind": "RUN", "job_id": jid, "params": {"mode": "SIM"}}).status_code == 201
    for kind in ("PAUSE", "STOP"):                                                 # halting is never tied to a place
        assert client.post(f"{T}/robot-commands", headers=away, json={"kind": kind, "job_id": jid, "params": {}}).status_code == 201, kind
    assert _sql("select count(*) from robot_commands where job_id=:j and params->>'mode'='REAL'", j=jid) == 0

    sync(client, bearer(key))
    near = _real_cmd(client, tech[0], jid)                                         # the app that started the agent
    assert near.status_code == 201, near.text
    assert _real_cmd(client, tech[0], jid, "ALIGN_START", corner="TL").status_code == 201


def test_resuming_a_real_run_also_needs_the_workstation_but_a_simulated_one_does_not(client, cust, staff, mgr, wcat, robot, fresh_hub):
    tech, away = _two_logins(client)
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, cal=CAL_MOTION)
    key = session_key(client, tech, robot, "workstation-app-02")["key"]
    sync(client, bearer(key), status={"mode": "SIM", "busy": True})
    sim, sim_run = open_run(client, tech, jid)                                     # a simulated run is open
    assert sim.status_code == 201
    assert client.post(f"{T}/robot-commands", headers=away, json={"kind": "RESUME", "job_id": jid, "params": {}}).status_code == 201
    assert _close(client, tech, sim_run, "STOPPED", 2).status_code == 200

    real, _ = open_run(client, tech, jid, mode="REAL", authorized=True, plan_digest="a" * 64)
    assert real.status_code == 201, real.text
    sync(client, bearer(key), status={"mode": "REAL", "busy": True})
    for kind in ("RESUME", "PAPER_CHANGED"):
        far = client.post(f"{T}/robot-commands", headers=away, json={"kind": kind, "job_id": jid, "params": {}})
        assert far.status_code == 403 and _err(far) == "REAL_ONLY_AT_WORKSTATION", (kind, far.text)
    assert client.post(f"{T}/robot-commands", headers=tech[0], json={"kind": "RESUME", "job_id": jid, "params": {}}).status_code == 201
    assert client.post(f"{T}/robot-commands", headers=away, json={"kind": "STOP", "job_id": jid, "params": {}}).status_code == 201


# ---------------------------------------------------------------------------------------------- L1
def _real_copy(client, tech, jid):
    r, run = open_run(client, tech, jid, mode="REAL", authorized=True, plan_digest="a" * 64)
    assert r.status_code == 201, r.text
    assert _close(client, tech, run, "DONE", 10).status_code == 200
    return run


def test_a_simulated_run_on_a_real_robot_is_not_a_written_copy(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech, qty=2, cal=CAL_MOTION)
    assert _sql("select is_simulated from robots where id=:r", r=robot) is False       # a real arm
    for mode in ("SIM", "MOCK"):
        r, run = open_run(client, tech, jid, mode=mode)
        assert r.status_code == 201 and _close(client, tech, run, "DONE", 10).status_code == 200
    d = client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()
    assert d["copies_written"] == 0                                                   # nothing reached the paper
    r = _post(client, tech, jid, "finish")
    assert r.status_code == 409 and _err(r) == "RUN_EVIDENCE_REQUIRED", r.text
    assert r.json()["error"]["details"] == {"written": 0, "quantity": 2, "simulated_runs_not_counted": 2}
    assert "REAL" in r.json()["error"]["message"] and _status(jid) == "WRITING"

    _real_copy(client, tech, jid)
    r = _post(client, tech, jid, "finish")
    assert _err(r) == "COPIES_MISSING" and r.json()["error"]["details"] == {"written": 1, "quantity": 2, "simulated_runs_not_counted": 2}
    _real_copy(client, tech, jid)
    assert client.get(f"{M}/jobs/{jid}", headers=mgr).json()["copies_written"] == 2
    assert _post(client, tech, jid, "finish").status_code == 200 and _status(jid) == "WRITTEN"


def test_a_robot_marked_simulated_counts_its_finished_runs(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    _sql("update robots set is_simulated = true where id=:r returning 1", r=robot)       # the Manager's flag: no real arm here
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201 and _close(client, tech, run, "DONE", 10).status_code == 200
    assert client.get(f"{T}/jobs/{jid}", headers=tech[0]).json()["copies_written"] == 1
    assert _post(client, tech, jid, "finish").status_code == 200


def test_a_manager_may_still_record_written_when_only_simulated_runs_were_reported(client, cust, staff, mgr, wcat, robot, tech):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201 and _close(client, tech, run, "DONE", 10).status_code == 200
    assert _err(_post(client, tech, jid, "finish")) == "RUN_EVIDENCE_REQUIRED"
    r = client.post(f"{M}/jobs/{jid}/finish-override", headers=mgr, json={"reason": "Robot đã viết thật, máy trạm báo nhầm chế độ"})
    assert r.status_code == 200 and _status(jid) == "WRITTEN", r.text
    over = _sql("select new_value from audit_logs where action='JOB_FINISH_OVERRIDE' and entity_id=:j order by id desc limit 1", j=jid)
    assert over["copies_written"] == 0 and over["had_done_run"] is False


# ---------------------------------------------------------------------------------------------- L2
def test_a_run_is_reported_by_the_robots_agent_and_never_by_a_persons_login(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    body = {"run_id": "run-by-hand-01", "mode": "SIM", "dry_run": False, "total_strokes": 10}
    for who in (tech[0], mgr):                                                        # the technician's own login, a Manager's
        r = client.post(f"{T}/jobs/{jid}/runs", headers=who, json=body)
        assert r.status_code == 403, r.text
    by_hand = client.post(f"{T}/jobs/{jid}/runs", headers=tech[0], json=body)
    assert _err(by_hand) == "RUN_REPORT_AGENT_ONLY" and _sql("select count(*) from robot_runs where job_id=:j", j=jid) == 0

    r, run = open_run(client, tech, jid)                                              # the agent of this robot
    assert r.status_code == 201
    done = {"result": "DONE", "completed_strokes": 10, "total_strokes": 10}
    assert _err(client.patch(f"{T}/runs/{run}", headers=tech[0], json=done)) == "RUN_REPORT_AGENT_ONLY"
    assert _sql("select ended_at is null from robot_runs where run_id=:r", r=run)         # still open: nothing was faked

    # the agent of ANOTHER robot (the same technician holds a job there too) cannot report this run
    from tests.test_api_scheduling import _at, _robot, _sched
    from tests.test_api_payments import _paid
    other_robot = _robot()
    oid2, _, _ = _paid(client, cust, staff[0], wcat)
    jid2 = _sched(client, mgr, oid2, other_robot, tech[1], _at(2, 9)).json()["id"]
    wrong = client.patch(f"{T}/runs/{run}", headers=agent_h(jid2), json=done)
    assert wrong.status_code == 403 and _err(wrong) == "RUN_REPORT_WRONG_ROBOT", wrong.text

    assert client.patch(f"{T}/runs/{run}", headers=agent_h(run=run), json=done).status_code == 200
    _sql("update robots set is_simulated = true where id=:r returning 1", r=robot)
    assert _post(client, tech, jid, "finish").status_code == 200                       # the technician still records "written" themselves


def test_the_agent_reports_how_its_run_ended_even_after_the_job_is_over(client, cust, staff, mgr, wcat, robot, tech, fresh_hub):
    """The job was recorded as written by a Manager while the agent was cut off. Its late report must reach the run, not be
    turned away as "no active job" (the agent would keep sending it for ever)."""
    oid, jid = _running(client, cust, staff, mgr, wcat, robot, tech)
    r, run = open_run(client, tech, jid)
    assert r.status_code == 201
    _quiet(robot)
    assert client.post(f"{M}/jobs/{jid}/finish-override", headers=mgr, json={"reason": WHY}).status_code == 200
    assert _status(jid) == "WRITTEN" and _sql("select result from robot_runs where run_id=:r", r=run) == "UNKNOWN"

    late = _close(client, tech, run, "DONE", 10)
    assert late.status_code == 200 and late.json()["result"] == "DONE", late.text       # the placeholder is replaced by what happened
    again = _close(client, tech, run, "FAULT", 2)
    assert again.status_code == 409 and _err(again) == "RUN_ALREADY_CLOSED"              # a clear answer the agent can drop
