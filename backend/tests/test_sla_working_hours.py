"""
Unit tests for app/services/sla.py
Verifies:
- Friday 6:00 PM Urgent ticket is NOT breached on Sunday morning
- Skips weekends & festival holidays accurately
- Pauses correctly on WAITING_ON_CUSTOMER and resumes accurately
- Recalculates on priority escalation
"""

from datetime import datetime, date, time
from zoneinfo import ZoneInfo
import pytest
from app.services.sla import (
    IST,
    is_working_day,
    next_working_day,
    snap_to_working_window,
    end_of_working_day,
    add_working_minutes,
    working_minutes_between,
    calculate_initial_sla_deadlines,
    recalculate_sla_on_escalation,
)

def test_working_day_and_holidays():
    holidays = {date(2026, 11, 25)} # Wed holiday
    # Monday 2026-11-23 is working day
    assert is_working_day(date(2026, 11, 23), holidays) is True
    # Saturday 2026-11-28 is non-working
    assert is_working_day(date(2026, 11, 28), holidays) is False
    # Sunday 2026-11-29 is non-working
    assert is_working_day(date(2026, 11, 29), holidays) is False
    # Wed holiday is non-working
    assert is_working_day(date(2026, 11, 25), holidays) is False

    # Next working day from Tuesday 24th skips Wed 25th -> Thursday 26th
    assert next_working_day(date(2026, 11, 24), holidays) == date(2026, 11, 26)

def test_friday_evening_ticket_not_breached_on_sunday():
    """
    INC Test: Friday 6:00 PM (18:00 IST) Urgent ticket (2h response target).
    Friday has 30 mins left (18:00 to 18:30).
    The remaining 90 mins carry over to Monday 09:30 -> 11:00 AM IST.
    On Sunday morning, elapsed working minutes is ONLY 30 mins, so it's NOT breached.
    """
    holidays = set()
    friday_6pm = datetime(2026, 11, 20, 18, 0, 0, tzinfo=IST) # Nov 20, 2026 was Friday
    first_resp_due, resol_due = calculate_initial_sla_deadlines(friday_6pm, "URGENT", holidays)

    # 18:00 Friday + 120 working minutes:
    # 30 mins on Friday (until 18:30)
    # 90 mins on Monday (09:30 + 1h30 = 11:00 IST)
    expected_resp_due = datetime(2026, 11, 23, 11, 0, 0, tzinfo=IST)
    assert first_resp_due == expected_resp_due

    # Sunday morning test (Sunday Nov 22, 10:00 AM)
    sunday_morning = datetime(2026, 11, 22, 10, 0, 0, tzinfo=IST)
    elapsed_working_mins = working_minutes_between(friday_6pm, sunday_morning, holidays)
    # Only Friday 18:00 to 18:30 should count (30 minutes)
    assert elapsed_working_mins == 30
    assert elapsed_working_mins < 120 # Not breached!

def test_add_working_minutes_across_days_and_holidays():
    # Thursday Nov 26, 2026 17:30 IST (1 hour before close)
    # Friday Nov 27 is holiday
    holidays = {date(2026, 11, 27)}
    thursday_evening = datetime(2026, 11, 26, 17, 30, 0, tzinfo=IST)

    # Add 120 working mins:
    # 60 mins Thursday (17:30 - 18:30)
    # Friday Nov 27 is holiday
    # Saturday Nov 28 is weekend
    # Sunday Nov 29 is weekend
    # Next is Monday Nov 30: 09:30 + 60 mins -> 10:30 IST
    due = add_working_minutes(thursday_evening, 120, holidays)
    expected = datetime(2026, 11, 30, 10, 30, 0, tzinfo=IST)
    assert due == expected

def test_urgent_late_evening_edge_case():
    """
    If created after 16:30 (e.g. 17:30 IST), ensure at least 2 working hours / same-day handling:
    max(end_of_working_day(effective_start), add_working_minutes(effective_start, 120))
    17:30 has 60 mins left today. 120 mins spans into next day 10:30.
    """
    holidays = set()
    wed_1730 = datetime(2026, 11, 25, 17, 30, 0, tzinfo=IST)
    first_resp_due, resol_due = calculate_initial_sla_deadlines(wed_1730, "URGENT", holidays)

    expected_resp_due = datetime(2026, 11, 26, 10, 30, 0, tzinfo=IST)
    assert first_resp_due == expected_resp_due
    assert resol_due == expected_resp_due

def test_sla_pause_and_resume():
    """
    Ticket created Monday 10:00 IST.
    Paused Monday 11:00 IST (elapsed 60 mins).
    Customer replies Tuesday 10:00 IST (paused for 7.5 hours Monday + 30 mins Tuesday = 8 working hours = 480 mins).
    """
    holidays = set()
    paused_at = datetime(2026, 11, 23, 11, 0, 0, tzinfo=IST)
    resumed_at = datetime(2026, 11, 24, 10, 0, 0, tzinfo=IST)

    paused_mins = working_minutes_between(paused_at, resumed_at, holidays)
    # Monday 11:00 to 18:30 = 7.5 hrs = 450 mins
    # Tuesday 09:30 to 10:00 = 30 mins
    # Total = 480 working mins
    assert paused_mins == 480

def test_priority_escalation_recalculation():
    """
    Ticket created as LOW at Monday 10:00 IST.
    Escalated to URGENT at Tuesday 10:00 IST.
    Budget for URGENT is 120 mins first response.
    From created_at (Monday 10:00 IST) + 120 mins = Monday 12:00 IST.
    Since Tuesday 10:00 is past Monday 12:00, it is immediately recognized as breached!
    """
    holidays = set()
    created_at = datetime(2026, 11, 23, 10, 0, 0, tzinfo=IST)
    new_resp_due, new_resol_due = recalculate_sla_on_escalation(
        created_at=created_at,
        new_priority="URGENT",
        total_paused_working_minutes=0,
        first_responded_at=None,
        holidays=holidays
    )

    expected_resp_due = datetime(2026, 11, 23, 12, 0, 0, tzinfo=IST)
    assert new_resp_due == expected_resp_due
