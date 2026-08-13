"""Core recurrence model for Repeatable Dates."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum, IntEnum
from typing import Iterable, Iterator, Literal


DateLike = date | datetime | str
Kind = Literal["once", "weekly", "monthly", "yearly"]


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class Overflow(str, Enum):
    """How invalid month days such as February 31 are handled."""

    CLAMP = "clamp"
    SKIP = "skip"


def _as_date(value: DateLike, name: str = "date") -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from exc
    raise TypeError(f"{name} must be a date, datetime, or ISO date string")


def _unique_ints(values: Iterable[int], *, minimum: int, maximum: int, name: str) -> tuple[int, ...]:
    result = tuple(sorted(set(values)))
    if not result:
        raise ValueError(f"{name} cannot be empty")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum for value in result):
        raise ValueError(f"{name} must contain integers from {minimum} through {maximum}")
    return result


@dataclass(frozen=True)
class Schedule:
    """An immutable recurring-date rule.

    Use the named constructors rather than instantiating this class directly.
    Query ranges are half-open: the start is included and the end is excluded.
    """

    kind: Kind
    anchor: date
    days: tuple[int, ...] = ()
    months: tuple[int, ...] = ()
    interval: int = 1
    until: date | None = None
    overflow: Overflow = Overflow.CLAMP

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError("interval must be at least 1")
        if self.until is not None and self.until < self.anchor:
            raise ValueError("until cannot be earlier than the schedule start")

    @classmethod
    def once(cls, on: DateLike) -> Schedule:
        occurrence = _as_date(on, "on")
        return cls(kind="once", anchor=occurrence)

    @classmethod
    def weekly(
        cls,
        *,
        start: DateLike,
        weekdays: Iterable[Weekday | int],
        every: int = 1,
        until: DateLike | None = None,
    ) -> Schedule:
        anchor = _as_date(start, "start")
        raw_weekdays = tuple(weekdays)
        if any(isinstance(day, bool) for day in raw_weekdays):
            raise ValueError("weekdays must contain weekday values from 0 through 6")
        normalized = _unique_ints((int(day) for day in raw_weekdays), minimum=0, maximum=6, name="weekdays")
        return cls(kind="weekly", anchor=anchor, days=normalized, interval=every, until=_as_date(until, "until") if until is not None else None)

    @classmethod
    def monthly(
        cls,
        *,
        start: DateLike,
        days: Iterable[int],
        every: int = 1,
        until: DateLike | None = None,
        overflow: Overflow | str = Overflow.CLAMP,
    ) -> Schedule:
        anchor = _as_date(start, "start")
        normalized = _unique_ints(days, minimum=1, maximum=31, name="days")
        return cls(kind="monthly", anchor=anchor, days=normalized, interval=every, until=_as_date(until, "until") if until is not None else None, overflow=Overflow(overflow))

    @classmethod
    def yearly(
        cls,
        *,
        start: DateLike,
        months: Iterable[int],
        days: Iterable[int],
        every: int = 1,
        until: DateLike | None = None,
        overflow: Overflow | str = Overflow.CLAMP,
    ) -> Schedule:
        anchor = _as_date(start, "start")
        normalized_months = _unique_ints(months, minimum=1, maximum=12, name="months")
        normalized_days = _unique_ints(days, minimum=1, maximum=31, name="days")
        return cls(kind="yearly", anchor=anchor, months=normalized_months, days=normalized_days, interval=every, until=_as_date(until, "until") if until is not None else None, overflow=Overflow(overflow))

    def between(self, start: DateLike, end: DateLike) -> list[date]:
        """Return occurrences in the half-open range ``[start, end)``."""

        range_start = _as_date(start, "start")
        range_end = _as_date(end, "end")
        if range_end <= range_start:
            raise ValueError("end must be later than start")
        effective_start = max(range_start, self.anchor)
        effective_end = min(range_end, self.until + timedelta(days=1)) if self.until is not None else range_end
        if effective_end <= effective_start:
            return []
        return list(self._occurrences(effective_start, effective_end))

    def next(self, after: DateLike, *, inclusive: bool = False) -> date | None:
        """Return the first occurrence after a date, or on it when inclusive."""

        point = _as_date(after, "after")
        if point == date.max and not inclusive:
            return None
        start = point if inclusive else point + timedelta(days=1)
        end = self.until + timedelta(days=1) if self.until is not None else date.max
        if end <= start:
            return None
        return next(self._occurrences(max(start, self.anchor), end), None)

    def _occurrences(self, start: date, end: date) -> Iterator[date]:
        if self.kind == "once":
            if start <= self.anchor < end:
                yield self.anchor
            return
        if self.kind == "weekly":
            yield from self._weekly(start, end)
        elif self.kind == "monthly":
            yield from self._monthly(start, end)
        else:
            yield from self._yearly(start, end)

    def _weekly(self, start: date, end: date) -> Iterator[date]:
        week_anchor = self.anchor - timedelta(days=self.anchor.weekday())
        cursor = start
        while cursor < end:
            weeks = (cursor - week_anchor).days // 7
            if weeks >= 0 and weeks % self.interval == 0 and cursor.weekday() in self.days:
                yield cursor
            cursor += timedelta(days=1)

    def _monthly(self, start: date, end: date) -> Iterator[date]:
        year, month = self.anchor.year, self.anchor.month
        index = 0
        while date(year, month, 1) < end:
            if index % self.interval == 0:
                for occurrence in self._month_dates(year, month):
                    if start <= occurrence < end and occurrence >= self.anchor:
                        yield occurrence
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            index += 1

    def _yearly(self, start: date, end: date) -> Iterator[date]:
        year = self.anchor.year
        while date(year, 1, 1) < end:
            if (year - self.anchor.year) % self.interval == 0:
                for month in self.months:
                    for occurrence in self._month_dates(year, month):
                        if start <= occurrence < end and occurrence >= self.anchor:
                            yield occurrence
            year += 1

    def _month_dates(self, year: int, month: int) -> Iterator[date]:
        last_day = calendar.monthrange(year, month)[1]
        seen: set[int] = set()
        for requested_day in self.days:
            if requested_day > last_day and self.overflow is Overflow.SKIP:
                continue
            actual_day = min(requested_day, last_day)
            if actual_day not in seen:
                seen.add(actual_day)
                yield date(year, month, actual_day)
