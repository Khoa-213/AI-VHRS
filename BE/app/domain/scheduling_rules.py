"""Pure scheduling rules (FR-37, FR-40, BR-18): working calendar, job duration, earliest free slot.

Jobs are continuous wall-clock intervals [start, end). A job that does not fit in one working day is stretched
over the following working days (the robot is not left running unattended overnight), so its interval also blocks
the robot and the technician for the nights in between.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from typing import Any, Sequence

DEFAULT_WORKING_HOURS = {"days": [1, 2, 3, 4, 5, 6], "start": "08:00", "end": "17:00", "utc_offset_min": 420}
DEFAULT_PREP_MIN = 15          # FR-40: preparation before writing
DEFAULT_PHOTO_MIN = 5          # FR-40: photographing after writing
SLOT_STEP_MIN = 5
HORIZON_DAYS = 120

Interval = tuple[datetime, datetime]


class NoSlotError(RuntimeError):
    pass


def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class WorkCalendar:
    tz: timezone
    days: frozenset[int]          # ISO weekdays, Monday = 1
    start: time
    end: time

    @classmethod
    def from_setting(cls, value: dict[str, Any] | None) -> "WorkCalendar":
        v = {**DEFAULT_WORKING_HOURS, **(value or {})}
        cal = cls(tz=timezone(timedelta(minutes=int(v["utc_offset_min"]))), days=frozenset(int(d) for d in v["days"]),
                  start=_hm(v["start"]), end=_hm(v["end"]))
        if not cal.days or not all(1 <= d <= 7 for d in cal.days) or cal.end <= cal.start:
            raise ValueError("invalid working_hours setting")
        return cal

    def _window(self, day: date) -> Interval:
        return (datetime.combine(day, self.start, self.tz), datetime.combine(day, self.end, self.tz))

    def next_open(self, moment: datetime) -> datetime:
        """Smallest instant >= moment that lies inside working hours."""
        local = moment.astimezone(self.tz)
        day = local.date()
        for _ in range(15):
            if day.isoweekday() in self.days:
                start, end = self._window(day)
                if local < start:
                    return start
                if local < end:
                    return local
            day += timedelta(days=1)
            local = datetime.combine(day, time(0), self.tz)
        raise NoSlotError("no working day found")

    def add_working_minutes(self, start: datetime, minutes: int) -> datetime:
        """End instant of `minutes` of work begun at `start` (which must be inside working hours)."""
        cur, remaining = self.next_open(start), minutes
        while True:
            end_today = self._window(cur.astimezone(self.tz).date())[1]
            room = (end_today - cur).total_seconds() / 60
            if remaining <= room:
                return cur + timedelta(minutes=remaining)
            remaining -= room
            cur = self.next_open(end_today)


def job_minutes(writing_sec_per_copy: int, quantity: int, prep_min: int = DEFAULT_PREP_MIN,
                photo_min: int = DEFAULT_PHOTO_MIN) -> int:
    """FR-40: duration = writing time x Q + preparation + photographing (at least 1 minute of writing)."""
    return max(1, ceil(writing_sec_per_copy * quantity / 60)) + prep_min + photo_min


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _round_up(moment: datetime, step_min: int) -> datetime:
    base = moment.replace(second=0, microsecond=0)
    if base < moment:
        base += timedelta(minutes=1)
    extra = (-(base.minute)) % step_min
    return base + timedelta(minutes=extra)


def find_slot(cal: WorkCalendar, earliest: datetime, minutes: int, busy: Sequence[Interval]) -> Interval:
    """Earliest working-time slot of `minutes` that overlaps none of the busy intervals."""
    limit = earliest + timedelta(days=HORIZON_DAYS)
    start = cal.next_open(_round_up(earliest, SLOT_STEP_MIN))
    while start < limit:
        end = cal.add_working_minutes(start, minutes)
        clash = [b for b in busy if overlaps((start, end), b)]
        if not clash:
            return start, end
        start = cal.next_open(_round_up(max(b[1] for b in clash), SLOT_STEP_MIN))
    raise NoSlotError("no free slot within the planning horizon")
