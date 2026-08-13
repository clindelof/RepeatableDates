import unittest
from datetime import date

from repeatable_dates import (
    Adjustment,
    BusinessCalendar,
    Collision,
    Overflow,
    Schedule,
    Weekday,
)


class AdvancedFeatureTests(unittest.TestCase):
    def test_first_second_and_last_weekdays(self):
        first = Schedule.monthly_weekday(
            start="2026-01-01", weekday=Weekday.MONDAY, occurrence=1
        )
        second = Schedule.monthly_weekday(
            start="2026-01-01", weekday=Weekday.MONDAY, occurrence=2
        )
        last = Schedule.monthly_weekday(
            start="2026-01-01", weekday=Weekday.FRIDAY, occurrence=-1
        )
        self.assertEqual([date(2026, 1, 5)], first.between("2026-01-01", "2026-02-01"))
        self.assertEqual([date(2026, 1, 12)], second.between("2026-01-01", "2026-02-01"))
        self.assertEqual([date(2026, 1, 30)], last.between("2026-01-01", "2026-02-01"))

    def test_missing_fifth_weekday_is_skipped(self):
        schedule = Schedule.monthly_weekday(
            start="2026-02-01", weekday=Weekday.MONDAY, occurrence=5
        )
        self.assertEqual([], schedule.between("2026-02-01", "2026-03-01"))

    def test_ordinal_weekday_supports_month_intervals(self):
        schedule = Schedule.monthly_weekday(
            start="2026-01-01", weekday=Weekday.MONDAY, occurrence=1, every=2
        )
        self.assertEqual(
            [date(2026, 1, 5), date(2026, 3, 2), date(2026, 5, 4)],
            schedule.between("2026-01-01", "2026-06-01"),
        )

    def test_occurrence_limit_is_counted_from_schedule_start(self):
        schedule = Schedule.weekly(
            start="2026-01-01",
            weekdays=[Weekday.MONDAY, Weekday.FRIDAY],
            count=3,
        )
        self.assertEqual(
            [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 9)],
            schedule.between("2026-01-01", "2026-02-01"),
        )
        self.assertEqual(
            [date(2026, 1, 9)],
            schedule.between("2026-01-06", "2026-02-01"),
        )

    def test_include_and_exclude_apply_after_adjustment(self):
        schedule = Schedule.once("2026-07-04")
        self.assertEqual(
            [date(2026, 7, 6)],
            schedule.between(
                "2026-07-01",
                "2026-07-10",
                adjustment=Adjustment.PREVIOUS_WEEKDAY,
                exclude=["2026-07-03"],
                include=["2026-07-06"],
            ),
        )

    def test_included_date_obeys_collision_policy(self):
        schedule = Schedule.once("2026-07-06")
        self.assertEqual(
            [date(2026, 7, 6)],
            schedule.between(
                "2026-07-01",
                "2026-07-10",
                include=["2026-07-06"],
                collisions=Collision.DEDUPLICATE,
            ),
        )

    def test_iteration_is_lazy_and_take_limits_results(self):
        schedule = Schedule.monthly(start="2026-01-01", days=[1])
        iterator = schedule.iter_between("2026-01-01", "9999-01-01")
        self.assertEqual(date(2026, 1, 1), next(iterator))
        self.assertEqual(
            [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
            schedule.take(3, after="2026-01-01", inclusive=True),
        )

    def test_count_between_uses_final_occurrences(self):
        schedule = Schedule.weekly(
            start="2026-01-01",
            weekdays=[Weekday.SATURDAY, Weekday.SUNDAY],
        )
        self.assertEqual(
            2,
            schedule.count_between(
                "2026-01-01",
                "2026-01-12",
                adjustment=Adjustment.PREVIOUS_WEEKDAY,
                collisions=Collision.DEDUPLICATE,
            ),
        )

    def test_schedule_serialization_round_trips_all_rule_types(self):
        schedules = [
            Schedule.once("2026-04-10"),
            Schedule.weekly(
                start="2026-01-01",
                weekdays=[Weekday.MONDAY, Weekday.FRIDAY],
                every=2,
                count=8,
            ),
            Schedule.monthly(
                start="2026-01-15",
                days=[15, 31],
                until="2027-01-01",
                overflow=Overflow.SKIP,
            ),
            Schedule.monthly_weekday(
                start="2026-01-01",
                weekday=Weekday.THURSDAY,
                occurrence=-1,
            ),
            Schedule.yearly(
                start="2026-01-01",
                months=[3, 9],
                days=[10],
                every=2,
            ),
        ]
        for schedule in schedules:
            with self.subTest(kind=schedule.kind):
                self.assertEqual(schedule, Schedule.from_dict(schedule.to_dict()))

    def test_serialization_rejects_unknown_type(self):
        with self.assertRaises(ValueError):
            Schedule.from_dict({"type": "sometimes", "start": "2026-01-01"})

    def test_business_calendars_can_be_combined(self):
        federal = BusinessCalendar(holidays=["2026-07-03"])
        company = BusinessCalendar(holidays=["2026-07-06"])
        combined = federal | company
        self.assertFalse(combined.is_business_day("2026-07-03"))
        self.assertFalse(combined.is_business_day("2026-07-06"))
        self.assertTrue(combined.is_business_day("2026-07-07"))

    def test_invalid_occurrence_limits_and_ordinals_are_rejected(self):
        with self.assertRaises(ValueError):
            Schedule.monthly(start="2026-01-01", days=[1], count=0)
        with self.assertRaises(ValueError):
            Schedule.monthly_weekday(
                start="2026-01-01",
                weekday=Weekday.MONDAY,
                occurrence=0,
            )


if __name__ == "__main__":
    unittest.main()
