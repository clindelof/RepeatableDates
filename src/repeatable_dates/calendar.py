"""Business-day calendars and date-adjustment policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Iterable


CalendarDate = date | datetime | str


class Adjustment(str, Enum):
    NONE = "none"
    PREVIOUS_WEEKDAY = "previous_weekday"
    NEXT_WEEKDAY = "next_weekday"
    NEAREST_WEEKDAY = "nearest_weekday"


class Collision(str, Enum):
    """How multiple occurrences adjusted onto the same date are handled."""

    KEEP = "keep"
    DEDUPLICATE = "deduplicate"
    ERROR = "error"


class CollisionError(ValueError):
    """Raised when adjusted occurrences collide under the error policy."""


def _calendar_date(value: CalendarDate) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("holidays must use ISO dates (YYYY-MM-DD)") from exc
    raise TypeError("holidays must be dates, datetimes, or ISO date strings")


@dataclass(frozen=True)
class BusinessCalendar:
    """Defines non-working weekdays and custom holiday dates."""

    holidays: frozenset[date] = field(default_factory=frozenset)
    weekend: frozenset[int] = field(default_factory=lambda: frozenset({5, 6}))

    def __init__(
        self,
        holidays: Iterable[CalendarDate] = (),
        weekend: Iterable[int] = (5, 6),
    ) -> None:
        normalized_weekend = frozenset(weekend)
        if any(isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6 for day in normalized_weekend):
            raise ValueError("weekend must contain weekday integers from 0 through 6")
        if len(normalized_weekend) == 7:
            raise ValueError("weekend cannot contain every day of the week")
        object.__setattr__(self, "holidays", frozenset(_calendar_date(day) for day in holidays))
        object.__setattr__(self, "weekend", normalized_weekend)

    def is_business_day(self, value: CalendarDate) -> bool:
        day = _calendar_date(value)
        return day.weekday() not in self.weekend and day not in self.holidays

    def adjust(self, value: CalendarDate, policy: Adjustment | str = Adjustment.NONE) -> date:
        day = _calendar_date(value)
        selected = Adjustment(policy)
        if selected is Adjustment.NONE or self.is_business_day(day):
            return day
        if selected is Adjustment.PREVIOUS_WEEKDAY:
            return self._seek(day, -1)
        if selected is Adjustment.NEXT_WEEKDAY:
            return self._seek(day, 1)
        return self._nearest(day)

    @property
    def search_padding(self) -> int:
        """A safe query expansion for this finite holiday calendar."""

        return len(self.holidays) + len(self.weekend) + 7

    def _seek(self, value: date, direction: int) -> date:
        cursor = value
        while True:
            if direction < 0 and cursor == date.min:
                raise OverflowError("no earlier business day is representable")
            if direction > 0 and cursor == date.max:
                raise OverflowError("no later business day is representable")
            cursor += timedelta(days=direction)
            if self.is_business_day(cursor):
                return cursor

    def _nearest(self, value: date) -> date:
        distance = 1
        while True:
            previous = value - timedelta(days=distance) if (value - date.min).days >= distance else None
            following = value + timedelta(days=distance) if (date.max - value).days >= distance else None
            # Previous wins a tie so the policy is deterministic.
            if previous is not None and self.is_business_day(previous):
                return previous
            if following is not None and self.is_business_day(following):
                return following
            if previous is None and following is None:
                raise OverflowError("no business day is representable")
            distance += 1
