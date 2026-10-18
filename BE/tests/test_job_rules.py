"""Phase 4a pure rules: job state machine, workstation events, calibration checks, stock. No database."""
import pytest

from app.domain import job_rules as jr
from app.models.ops import JobEventType as E
from app.models.ops import JobStatus as S

GOOD_POINTS = [{"x": 0, "y": 0, "z": 10}, {"x": 100, "y": 0, "z": 10.1}, {"x": 0, "y": 100, "z": 10.2}]
GOOD_CHECKLIST = {k: True for k in jr.REQUIRED_CHECKLIST}


# ---- state machine ----------------------------------------------------------------------------------
def test_technician_transitions():
    ok = [(S.SCHEDULED, S.PREPARING), (S.PREPARING, S.WRITING), (S.PREPARING, S.FAILED), (S.WRITING, S.PAUSED),
          (S.WRITING, S.WRITTEN), (S.WRITING, S.FAILED), (S.PAUSED, S.WRITING), (S.PAUSED, S.FAILED)]
    for a, b in ok:
        assert jr.can_move(a, b), (a, b)
    bad = [(S.SCHEDULED, S.WRITING), (S.SCHEDULED, S.FAILED), (S.PREPARING, S.WRITTEN), (S.PAUSED, S.WRITTEN),
           (S.WRITTEN, S.WRITING), (S.FAILED, S.WRITING), (S.CANCELLED, S.PREPARING), (S.WRITING, S.PREPARING)]
    for a, b in bad:
        assert not jr.can_move(a, b), (a, b)


def test_every_open_status_but_scheduled_can_take_an_incident():
    assert set(jr.INCIDENT_FROM) == {S.PREPARING, S.WRITING, S.PAUSED}
    for s in jr.INCIDENT_FROM:
        assert jr.can_move(s, S.FAILED)
    assert not jr.can_move(S.SCHEDULED, S.FAILED)


# ---- workstation events ---------------------------------------------------------------------------------
def test_event_effects():
    assert jr.event_effect(E.PAUSE, S.WRITING) == S.PAUSED
    assert jr.event_effect(E.RESUME, S.PAUSED) == S.WRITING
    assert jr.event_effect(E.PROGRESS, S.WRITING) is None
    for e in (E.ESTOP, E.OVER_FORCE, E.STROKE_LOST, E.SENSOR_LOST):          # FR-48: auto PAUSED on anything abnormal
        assert jr.event_effect(e, S.WRITING) == S.PAUSED
        assert jr.event_effect(e, S.PAUSED) is None                          # already paused: log only
    assert jr.event_effect(E.FORCE_SUMMARY, S.WRITTEN) is None


@pytest.mark.parametrize("event,status", [(E.PROGRESS, S.PAUSED), (E.PROGRESS, S.PREPARING), (E.PAUSE, S.PAUSED),
                                          (E.RESUME, S.WRITING), (E.ESTOP, S.SCHEDULED), (E.FORCE_SUMMARY, S.FAILED),
                                          (E.OVER_FORCE, S.WRITTEN)])
def test_events_in_the_wrong_state_are_refused(event, status):
    with pytest.raises(jr.JobRuleError) as exc:
        jr.event_effect(event, status)
    assert exc.value.code == "JOB_STATE_CONFLICT"


@pytest.mark.parametrize("event", [E.DOWNLOADED, E.HASH_MISMATCH, E.CALIBRATED, E.SIMULATED, E.START, E.WRITTEN, E.INCIDENT])
def test_server_side_events_cannot_be_posted(event):
    with pytest.raises(jr.JobRuleError) as exc:
        jr.event_effect(event, S.WRITING)
    assert exc.value.code == "EVENT_NOT_ALLOWED"


def test_every_event_type_is_either_client_or_server_side():
    assert set(jr.CLIENT_EVENTS) | {E.DOWNLOADED, E.HASH_MISMATCH, E.CALIBRATED, E.SIMULATED, E.START, E.WRITTEN,
                                    E.INCIDENT} == set(E)


# ---- calibration ----------------------------------------------------------------------------------------
def test_checklist_needs_every_item_true():
    jr.check_checklist(GOOD_CHECKLIST)
    for key in jr.REQUIRED_CHECKLIST:
        with pytest.raises(jr.JobRuleError) as exc:
            jr.check_checklist({**GOOD_CHECKLIST, key: False})
        assert exc.value.code == "CHECKLIST_INCOMPLETE" and exc.value.details == {"missing": [key]}
    with pytest.raises(jr.JobRuleError):
        jr.check_checklist({})
    with pytest.raises(jr.JobRuleError):
        jr.check_checklist({**GOOD_CHECKLIST, "pen_installed": 1})           # truthy but not True


def test_probe_points():
    jr.check_probe_points(GOOD_POINTS)
    jr.check_probe_points(GOOD_POINTS + [{"x": 50, "y": 50, "z": 10.1}] * 10)  # grid points are allowed
    bad = {
        "too few": GOOD_POINTS[:2],
        "too many": GOOD_POINTS * 200,
        "missing z": [{"x": 0, "y": 0}, *GOOD_POINTS[1:]],
        "string": [{"x": "0", "y": 0, "z": 1}, *GOOD_POINTS[1:]],
        "bool": [{"x": True, "y": 0, "z": 1}, *GOOD_POINTS[1:]],
        "nan": [{"x": float("nan"), "y": 0, "z": 1}, *GOOD_POINTS[1:]],
        "collinear": [{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 1, "z": 1}, {"x": 2, "y": 2, "z": 2}],
        "same point": [GOOD_POINTS[0]] * 3,
        "not a dict": [1, 2, 3],
    }
    for name, pts in bad.items():
        with pytest.raises(jr.JobRuleError) as exc:
            jr.check_probe_points(pts)
        assert exc.value.code == "INVALID_PROBE_POINTS", name


# ---- simulation, force summary --------------------------------------------------------------------------
def test_simulation_cannot_pass_with_errors():
    jr.check_simulation(True, [])
    jr.check_simulation(False, ["reach"])
    jr.check_simulation(False, [])
    with pytest.raises(jr.JobRuleError) as exc:
        jr.check_simulation(True, ["singularity at stroke 4"])
    assert exc.value.code == "SIMULATION_INCONSISTENT"


def test_force_summary():
    jr.check_force_summary({"f_mean": 1.0, "f_max": 1.5, "rms_err_pct": 4.2, "in_band_pct": 97.5, "samples": 5000})
    jr.check_force_summary({"f_max": 2})
    for bad in ({}, {"f_mean": "1"}, {"f_mean": True}, {"nope": 1}, {"in_band_pct": 120}, {"in_band_pct": -1},
                {"f_max": float("inf")}):
        with pytest.raises(jr.JobRuleError) as exc:
            jr.check_force_summary(bad)
        assert exc.value.code == "INVALID_FORCE_SUMMARY", bad


# ---- stock ---------------------------------------------------------------------------------------------
def test_stock_use_and_deduct():
    assert jr.stock_use(3, 2) == jr.StockUse(paper=6, pen=1, ink=1)
    assert jr.stock_use(1, 1) == jr.StockUse(paper=1, pen=1, ink=1)
    assert jr.stock_use(0, 0) == jr.StockUse(paper=1, pen=1, ink=1)           # never zero consumption
    assert jr.deduct(10, 4) == (6, 0)
    assert jr.deduct(4, 4) == (0, 0)
    assert jr.deduct(3, 5) == (0, 2)                                         # cannot go below 0; the gap is reported
    assert jr.deduct(0, 1) == (0, 1)
