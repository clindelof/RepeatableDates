"""Core recurrence model for Repeatable Dates."""

from __future__ import annotations

import calendar as calendar_module
import heapq
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum, IntEnum
from itertools import islice
from typing import Any, Iterable, Iterator, Literal, Mapping

from .calendar import Adjustment, BusinessCalendar, Collision, CollisionError


DateLike = date | datetime | str
Kind = Literal["once", "weekly", "monthly", "monthly_weekday", "yearly"]


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


def _weekday(value: Weekday | int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= int(value) <= 6:
        raise ValueError("weekday must be a value from 0 through 6")
    return int(value)


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
    count: int | None = None
    overflow: Overflow = Overflow.CLAMP
    weekday: int | None = None
    ordinal: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.interval, bool) or self.interval < 1:
            raise ValueError("interval must be at least 1")
        if self.until is not None and self.until < self.anchor:
            raise ValueError("until cannot be earlier than the schedule start")
        if self.count is not None and (isinstance(self.count, bool) or self.count < 1):
            raise ValueError("count must be at least 1")

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
        count: int | None = None,
    ) -> Schedule:
        raw_weekdays = tuple(weekdays)
        if any(isinstance(day, bool) for day in raw_weekdays):
            raise ValueError("weekdays must contain weekday values from 0 through 6")
        normalized = _unique_ints((int(day) for day in raw_weekdays), minimum=0, maximum=6, name="weekdays")
        return cls(
            kind="weekly",
            anchor=_as_date(start, "start"),
            days=normalized,
            interval=every,
            until=_optional_date(until, "until"),
            count=count,
        )

    @classmethod
    def monthly(
        cls,
        *,
        start: DateLike,
        days: Iterable[int],
        every: int = 1,
        until: DateLike | None = None,
        count: int | None = None,
        overflow: Overflow | str = Overflow.CLAMP,
    ) -> Schedule:
        return cls(
            kind="monthly",
            anchor=_as_date(start, "start"),
            days=_unique_ints(days, minimum=1, maximum=31, name="days"),
            interval=every,
            until=_optional_date(until, "until"),
            count=count,
            overflow=Overflow(overflow),
        )

    @classmethod
    def monthly_weekday(
        cls,
        *,
        start: DateLike,
        weekday: Weekday | int,
        occurrence: int,
        every: int = 1,
        until: DateLike | None = None,
        count: int | None = None,
    ) -> Schedule:
        """Repeat on the first through fifth, or last, weekday of a month."""

        if isinstance(occurrence, bool) or occurrence not in {-1, 1, 2, 3, 4, 5}:
            raise ValueError("occurrence must be 1 through 5, or -1 for last")
        return cls(
            kind="monthly_weekday",
            anchor=_as_date(start, "start"),
            interval=every,
            until=_optional_date(until, "until"),
            count=count,
            weekday=_weekday(weekday),
            ordinal=occurrence,
        )

    @classmethod
    def yearly(
        cls,
        *,
        start: DateLike,
        months: Iterable[int],
        days: Iterable[int],
        every: int = 1,
        until: DateLike | None = None,
        count: int | None = None,
        overflow: Overflow | str = Overflow.CLAMP,
    ) -> Schedule:
        return cls(
            kind="yearly",
            anchor=_as_date(start, "start"),
            months=_unique_ints(months, minimum=1, maximum=12, name="months"),
            days=_unique_ints(days, minimum=1, maximum=31, name="days"),
            interval=every,
            until=_optional_date(until, "until"),
            count=count,
            overflow=Overflow(overflow),
        )

    def between(self, start: DateLike, end: DateLike, **options: Any) -> list[date]:
        """Return occurrences in the half-open range ``[start, end)``."""

        return list(self.iter_between(start, end, **options))

    def iter_between(
        self,
        start: DateLike,
        end: DateLike,
        *,
        adjustment: Adjustment | str = Adjustment.NONE,
        calendar: BusinessCalendar | None = None,
        collisions: Collision | str = Collision.KEEP,
        include: Iterable[DateLike] = (),
        exclude: Iterable[DateLike] = (),
    ) -> Iterator[date]:
        """Lazily yield occurrences in the half-open range ``[start, end)``.

        Included and excluded dates apply to final, adjusted dates. Included
        dates are not themselves business-day adjusted.
        """

        range_start = _as_date(start, "start")
        range_end = _as_date(end, "end")
        if range_end <= range_start:
            raise ValueError("end must be later than start")

        selected_adjustment = Adjustment(adjustment)
        selected_collisions = Collision(collisions)
        business_calendar = calendar or BusinessCalendar()
        if selected_adjustment is Adjustment.NONE:
            generated: Iterable[date] = self._iter_raw(range_start, range_end)
        else:
            padding = business_calendar.search_padding
            expanded_start = _safe_shift(range_start, -padding)
            expanded_end = _safe_shift(range_end, padding)
            generated = (
                adjusted
                for adjusted in (
                    business_calendar.adjust(value, selected_adjustment)
                    for value in self._iter_raw(expanded_start, expanded_end)
                )
                if range_start <= adjusted < range_end
            )

        normalized_includes = {_as_date(value, "include") for value in include}
        included = sorted(value for value in normalized_includes if range_start <= value < range_end)
        excluded = {_as_date(value, "exclude") for value in exclude}
        merged = heapq.merge(generated, included)
        yield from _resolve_collisions((value for value in merged if value not in excluded), selected_collisions)

    def count_between(self, start: DateLike, end: DateLike, **options: Any) -> int:
        """Count occurrences without constructing a result list."""

        return sum(1 for _ in self.iter_between(start, end, **options))

    def take(
        self,
        amount: int,
        *,
        after: DateLike,
        inclusive: bool = False,
        **options: Any,
    ) -> list[date]:
        """Return at most ``amount`` occurrences from a point in time."""

        if isinstance(amount, bool) or amount < 0:
            raise ValueError("amount cannot be negative")
        if amount == 0:
            return []
        point = _as_date(after, "after")
        if point == date.max and not inclusive:
            return []
        start = point if inclusive else _safe_shift(point, 1)
        if start >= date.max:
            return []
        return list(islice(self.iter_between(start, date.max, **options), amount))

    def next(self, after: DateLike, *, inclusive: bool = False, **options: Any) -> date | None:
        """Return the first occurrence after a date, or on it when inclusive."""

        values = self.take(1, after=after, inclusive=inclusive, **options)
        return values[0] if values else None

    def to_dict(self) -> dict[str, Any]:
        """Return a stable, JSON-compatible representation of the schedule."""

        result: dict[str, Any] = {"type": self.kind, "start": self.anchor.isoformat()}
        if self.kind == "weekly":
            result["weekdays"] = list(self.days)
        elif self.kind == "monthly":
            result["days"] = list(self.days)
            result["overflow"] = self.overflow.value
        elif self.kind == "monthly_weekday":
            result["weekday"] = self.weekday
            result["occurrence"] = self.ordinal
        elif self.kind == "yearly":
            result["months"] = list(self.months)
            result["days"] = list(self.days)
            result["overflow"] = self.overflow.value
        if self.interval != 1:
            result["every"] = self.interval
        if self.until is not None:
            result["until"] = self.until.isoformat()
        if self.count is not None:
            result["count"] = self.count
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Schedule:
        """Reconstruct a schedule produced by :meth:`to_dict`."""

        if not isinstance(data, Mapping):
            raise TypeError("schedule data must be a mapping")
        kind = data.get("type")
        if kind == "once":
            return cls.once(data["start"])
        common = {
            "start": data["start"],
            "every": data.get("every", 1),
            "until": data.get("until"),
            "count": data.get("count"),
        }
        if kind == "weekly":
            return cls.weekly(weekdays=data["weekdays"], **common)
        if kind == "monthly":
            return cls.monthly(days=data["days"], overflow=data.get("overflow", Overflow.CLAMP), **common)
        if kind == "monthly_weekday":
            return cls.monthly_weekday(weekday=data["weekday"], occurrence=data["occurrence"], **common)
        if kind == "yearly":
            return cls.yearly(
                months=data["months"],
                days=data["days"],
                overflow=data.get("overflow", Overflow.CLAMP),
                **common,
            )
        raise ValueError(f"unsupported schedule type: {kind!r}")

    def _iter_raw(self, range_start: date, range_end: date) -> Iterator[date]:
        effective_start = max(range_start, self.anchor)
        effective_end = min(range_end, _safe_shift(self.until, 1)) if self.until is not None else range_end
        if effective_end <= effective_start:
            return
        if self.count is None:
            yield from self._occurrences(effective_start, effective_end)
            return
        limited = islice(self._occurrences(self.anchor, effective_end), self.count)
        yield from (value for value in limited if value >= effective_start)

    def _occurrences(self, start: date, end: date) -> Iterator[date]:
        if self.kind == "once":
            if start <= self.anchor < end:
                yield self.anchor
        elif self.kind == "weekly":
            yield from self._weekly(start, end)
        elif self.kind == "monthly":
            yield from self._monthly(start, end)
        elif self.kind == "monthly_weekday":
            yield from self._monthly_weekday(start, end)
        else:
            yield from self._yearly(start, end)

    def _weekly(self, start: date, end: date) -> Iterator[date]:
        week_anchor = self.anchor - timedelta(days=self.anchor.weekday())
        cursor = start
        while cursor < end:
            weeks = (cursor - week_anchor).days // 7
            if weeks >= 0 and weeks % self.interval == 0 and cursor.weekday() in self.days:
                yield cursor
            if cursor == date.max:
                break
            cursor += timedelta(days=1)

    def _monthly(self, start: date, end: date) -> Iterator[date]:
        for year, month in self._months_until(end):
            for occurrence in self._month_dates(year, month):
                if start <= occurrence < end and occurrence >= self.anchor:
                    yield occurrence

    def _monthly_weekday(self, start: date, end: date) -> Iterator[date]:
        for year, month in self._months_until(end):
            occurrence = self._ordinal_weekday_date(year, month)
            if occurrence is not None and start <= occurrence < end and occurrence >= self.anchor:
                yield occurrence

    def _months_until(self, end: date) -> Iterator[tuple[int, int]]:
        year, month = self.anchor.year, self.anchor.month
        index = 0
        while date(year, month, 1) < end:
            if index % self.interval == 0:
                yield year, month
            if year == 9999 and month == 12:
                break
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
            if year == 9999:
                break
            year += 1

    def _month_dates(self, year: int, month: int) -> Iterator[date]:
        last_day = calendar_module.monthrange(year, month)[1]
        seen: set[int] = set()
        for requested_day in self.days:
            if requested_day > last_day and self.overflow is Overflow.SKIP:
                continue
            actual_day = min(requested_day, last_day)
            if actual_day not in seen:
                seen.add(actual_day)
                yield date(year, month, actual_day)

    def _ordinal_weekday_date(self, year: int, month: int) -> date | None:
        assert self.weekday is not None and self.ordinal is not None
        last_day = calendar_module.monthrange(year, month)[1]
        if self.ordinal == -1:
            last = date(year, month, last_day)
            return date(year, month, last_day - ((last.weekday() - self.weekday) % 7))
        first = date(year, month, 1)
        day = 1 + ((self.weekday - first.weekday()) % 7) + (7 * (self.ordinal - 1))
        return date(year, month, day) if day <= last_day else None


def _optional_date(value: DateLike | None, name: str) -> date | None:
    return _as_date(value, name) if value is not None else None


def _safe_shift(value: date, days: int) -> date:
    if days < 0:
        return date.min if (value - date.min).days < -days else value + timedelta(days=days)
    return date.max if (date.max - value).days < days else value + timedelta(days=days)


def _resolve_collisions(values: Iterable[date], policy: Collision) -> Iterator[date]:
    previous: date | None = None
    for value in values:
        if previous == value:
            if policy is Collision.ERROR:
                raise CollisionError(f"multiple occurrences adjusted to {value.isoformat()}")
            if policy is Collision.DEDUPLICATE:
                continue
        yield value
        previous = value
