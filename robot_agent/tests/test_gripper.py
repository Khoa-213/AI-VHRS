"""Gripper serial protocol, force table and safety rules. No hardware."""
import pytest

from vhrs_agent.gripper import (FLAG_OVERFORCE, FLAG_SATURATED, FLAG_TOUCH, FLAG_UNCAL, ForceLimits, ForceTable,
                                FrameError, Sample, SafetyMonitor, checksum, encode, parse_event, parse_frame)

LIM = ForceLimits(f_min=0.6, f_target=1.0, f_max=1.6, f_hard=4.0)


def test_documented_example_frame_parses_and_checksum_is_xor():
    body = "F,10432,523117,18734,1125,0"
    line = encode(body)
    assert line == f"${body}*{checksum(body)}\n"
    s = parse_frame(line)
    assert (s.seq, s.t_ms, s.raw, s.force_mn, s.flags) == (10432, 523117, 18734, 1125, 0) and s.force_n == 1.125
    assert checksum("AB") == f"{ord('A') ^ ord('B'):02X}"


@pytest.mark.parametrize("line", ["F,1,2,3,4,0*00", "$F,1,2,3,4,0*00", "$F,1,2,3*7A", "$X,1,2,3,4,0*" + checksum("X,1,2,3,4,0"),
                                  "$F,a,2,3,4,0*" + checksum("F,a,2,3,4,0"), "garbage"])
def test_corrupt_frames_are_rejected_not_guessed(line):
    with pytest.raises(FrameError):
        parse_frame(line)


def test_events_parse():
    assert parse_event(encode("E,FAULT,3")) == ("FAULT", "3")
    assert parse_event(encode("E,ZERO_DRIFT,60")) == ("ZERO_DRIFT", "60")


def test_force_table_interpolates_and_refuses_to_extrapolate():
    t = ForceTable([(1000, 0), (2000, 400), (3000, 1000)])
    assert t.force_mn(1500) == 200.0 and t.force_mn(2500) == 700.0
    assert t.force_mn(999) is None and t.force_mn(3001) is None
    with pytest.raises(ValueError):
        ForceTable([(1, 1)])
    with pytest.raises(ValueError):
        ForceTable([(1, 1), (1, 2)])


def S(force_mn=1000, flags=FLAG_TOUCH, seq=1, rx=0.0):
    return Sample(seq, 0, 0, force_mn, flags, rx)


def test_monitor_rules():
    now = [10.0]
    m = SafetyMonitor(LIM, lambda: now[0])
    assert m.evaluate(S(rx=10.0), writing=True) is None
    assert m.evaluate(None, writing=True).code == "SENSOR_LOST"
    assert m.evaluate(S(rx=9.0), writing=True).code == "SENSOR_LOST"           # older than 100 ms
    assert m.evaluate(S(flags=FLAG_UNCAL, rx=10.0), writing=True).code == "SENSOR_LOST"
    f = m.evaluate(S(flags=FLAG_SATURATED, rx=10.0), writing=True)
    assert f.code == "OVER_FORCE" and f.stop
    assert m.evaluate(S(flags=FLAG_OVERFORCE, rx=10.0), writing=True).stop
    assert m.evaluate(S(force_mn=4100, rx=10.0), writing=True).code == "OVER_FORCE"
    assert m.evaluate(S(force_mn=3900, rx=10.0), writing=True) is None          # below F_hard: allowed by the monitor


def test_contact_loss_needs_more_than_60_ms_and_only_while_writing():
    now = [0.0]
    m = SafetyMonitor(LIM, lambda: now[0])

    def low():
        return S(force_mn=50, flags=0, rx=now[0])

    assert m.evaluate(low(), writing=True) is None
    now[0] = 0.050
    assert m.evaluate(low(), writing=True) is None
    now[0] = 0.070
    f = m.evaluate(low(), writing=True)
    assert f.code == "STROKE_LOST" and not f.stop                               # pause, do not crash on
    m.reset_contact()
    assert m.evaluate(low(), writing=False) is None                              # pen up: no force is expected
    now[0] = 1.0
    assert m.evaluate(S(force_mn=1000, rx=1.0), writing=True) is None


def test_dropped_frames_are_counted():
    m = SafetyMonitor(LIM, lambda: 0.0)
    for seq in (1, 2, 5):
        m.evaluate(S(seq=seq, rx=0.0), writing=False)
    assert m.dropped == 2
