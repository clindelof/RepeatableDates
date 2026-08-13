import unittest
from datetime import date, datetime

from repeatable_dates import Overflow, Schedule, Weekday


class ScheduleTests(unittest.TestCase):
    def test_once_is_inside_half_open_range(self):
        schedule = Schedule.once("2026-07-18")
        self.assertEqual([date(2026, 7, 18)], schedule.between("2026-07-01", "2026-08-01"))
        self.assertEqual([], schedule.between("2026-07-01", "2026-07-18"))

    def test_weekly_supports_selected_weekdays(self):
        schedule = Schedule.weekly(start="2026-01-01", weekdays=[Weekday.MONDAY, Weekday.FRIDAY])
        self.assertEqual(
            [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 9)],
            schedule.between("2026-01-01", "2026-01-10"),
        )

    def test_every_two_weeks_is_anchored_to_start_week(self):
        schedule = Schedule.weekly(start="2026-01-07", weekdays=[Weekday.WEDNESDAY], every=2)
        self.assertEqual(
            [date(2026, 1, 7), date(2026, 1, 21), date(2026, 2, 4)],
            schedule.between("2026-01-01", "2026-02-10"),
        )

    def test_monthly_clamps_to_end_of_month(self):
        schedule = Schedule.monthly(start="2028-01-01", days=[31])
        self.assertEqual(
            [date(2028, 1, 31), date(2028, 2, 29), date(2028, 3, 31)],
            schedule.between("2028-01-01", "2028-04-01"),
        )

    def test_monthly_can_skip_invalid_days(self):
        schedule = Schedule.monthly(start="2027-01-01", days=[31], overflow=Overflow.SKIP)
        self.assertEqual(
            [date(2027, 1, 31), date(2027, 3, 31)],
            schedule.between("2027-01-01", "2027-04-01"),
        )

    def test_clamped_duplicate_dates_are_removed(self):
        schedule = Schedule.monthly(start="2027-02-01", days=[28, 29, 30, 31])
        self.assertEqual([date(2027, 2, 28)], schedule.between("2027-02-01", "2027-03-01"))

    def test_selected_months_repeat_yearly(self):
        schedule = Schedule.yearly(start="2026-01-01", months=[1, 7], days=[15])
        self.assertEqual(
            [date(2026, 1, 15), date(2026, 7, 15), date(2027, 1, 15)],
            schedule.between("2026-01-01", "2027-02-01"),
        )

    def test_schedule_start_and_until_are_respected(self):
        schedule = Schedule.monthly(start="2026-01-20", days=[1, 20], until="2026-03-01")
        self.assertEqual(
            [date(2026, 1, 20), date(2026, 2, 1), date(2026, 2, 20), date(2026, 3, 1)],
            schedule.between("2026-01-01", "2026-04-01"),
        )

    def test_next_is_exclusive_by_default(self):
        schedule = Schedule.monthly(start="2026-01-01", days=[15])
        self.assertEqual(date(2026, 2, 15), schedule.next("2026-01-15"))
        self.assertEqual(date(2026, 1, 15), schedule.next("2026-01-15", inclusive=True))

    def test_next_returns_none_after_until(self):
        schedule = Schedule.weekly(start="2026-01-01", weekdays=[Weekday.FRIDAY], until="2026-01-31")
        self.assertIsNone(schedule.next("2026-02-01"))

    def test_next_after_largest_supported_date_is_none(self):
        schedule = Schedule.monthly(start="2026-01-01", days=[1])
        self.assertIsNone(schedule.next(date.max))

    def test_datetime_inputs_are_accepted(self):
        schedule = Schedule.once(datetime(2026, 5, 10, 14, 30))
        self.assertEqual([date(2026, 5, 10)], schedule.between(date(2026, 5, 1), date(2026, 6, 1)))

    def test_invalid_rules_are_rejected(self):
        with self.assertRaises(ValueError):
            Schedule.monthly(start="2026-01-01", days=[])
        with self.assertRaises(ValueError):
            Schedule.monthly(start="2026-01-01", days=[0])
        with self.assertRaises(ValueError):
            Schedule.weekly(start="2026-01-01", weekdays=[7])
        with self.assertRaises(ValueError):
            Schedule.weekly(start="2026-01-01", weekdays=[True])
        with self.assertRaises(ValueError):
            Schedule.weekly(start="2026-01-01", weekdays=[Weekday.MONDAY], every=0)
        with self.assertRaises(ValueError):
            Schedule.once("not-a-date")


if __name__ == "__main__":
    unittest.main()
