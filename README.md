# Repeatable Dates

Repeatable Dates is a small, dependency-free Python library for generating recurring dates. It provides explicit rules for one-time, weekly, monthly, and selected-month schedules without tying recurrence logic to a web framework or database.

The Python distribution and import names are `repeatable-dates` and `repeatable_dates`, respectively.

> **Status:** Early alpha. The public API may evolve before version 1.0.

## Features

- One-time occurrences
- Selected weekdays, including every-N-week schedules
- Selected days of every month or every N months
- Selected months and days, including every-N-year schedules
- Optional schedule start and end bounds
- Configurable handling of dates such as February 30: clamp to month-end or skip
- ISO strings, `date`, and `datetime` inputs
- Half-open range queries with predictable boundary behavior
- No runtime dependencies

## Installation for development

```bash
git clone https://github.com/clindelof/repeatable.git
cd repeatable
python -m venv .venv
python -m pip install -e .
```

## Usage

```python
from repeatable_dates import Schedule, Weekday

schedule = Schedule.weekly(
    start="2026-01-02",
    weekdays=[Weekday.FRIDAY],
    every=2,
)

schedule.between("2026-01-01", "2026-02-01")
# [date(2026, 1, 2), date(2026, 1, 16), date(2026, 1, 30)]
```

Monthly dates are clamped to the end of shorter months by default:

```python
schedule = Schedule.monthly(start="2028-01-01", days=[31])
schedule.between("2028-01-01", "2028-04-01")
# [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)]
```

Use `Overflow.SKIP` when an invalid calendar day should not produce an occurrence:

```python
from repeatable_dates import Overflow

schedule = Schedule.monthly(
    start="2027-01-01",
    days=[31],
    overflow=Overflow.SKIP,
)
```

Find the next occurrence:

```python
schedule.next("2027-01-31")
schedule.next("2027-01-31", inclusive=True)
```

## Range semantics

`between(start, end)` uses a half-open interval: `start` is included and `end` is excluded. A schedule's optional `until` date is inclusive.

All results are `datetime.date` values. When a `datetime` is supplied, its time component is intentionally discarded. Repeatable Dates models calendar recurrence, not time zones or times of day.

## Development

```bash
python -m unittest discover -s tests -v
```

The test suite uses only synthetic calendar dates and Python's standard library.

## Scope

Repeatable Dates does not currently implement time-of-day scheduling, time zones, cron expressions, or the full iCalendar recurrence-rule standard. The project favors a compact and understandable API over exhaustive recurrence syntax.

## License

[MIT](LICENSE)
