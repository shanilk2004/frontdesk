"""
SLA Engine for Frontdesk (Arvo Systems Support Platform)
Business Calendar: Asia/Kolkata (IST, UTC+05:30)
Working Days: Monday to Friday
Working Hours: 09:30 to 18:30 IST (9 working hours = 540 working minutes/day)
Non-Working Time: Weekends (Sat/Sun), outside 09:30-18:30 IST, and dates in the holidays table.
"""

from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Set, Tuple, Optional

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc
START_TIME = time(9, 30)   # 09:30 IST
END_TIME = time(18, 30)    # 18:30 IST
DAILY_WORKING_MINUTES = 540

def to_ist(dt: datetime) -> datetime:
    """Convert any datetime to timezone-aware IST datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)

def to_utc(dt: datetime) -> datetime:
    """Convert timezone-aware datetime to UTC datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

def is_working_day(d: date, holidays: Set[date]) -> bool:
    """Check if date is Mon-Fri and not in holidays."""
    if d.weekday() >= 5: # 5 = Saturday, 6 = Sunday
        return False
    if d in holidays:
        return False
    return True

def next_working_day(d: date, holidays: Set[date]) -> date:
    """Find the next working day starting from d + 1 day."""
    curr = d + timedelta(days=1)
    while not is_working_day(curr, holidays):
        curr += timedelta(days=1)
    return curr

def snap_to_working_window(dt: datetime, holidays: Set[date]) -> datetime:
    """
    If dt falls outside working hours or on a non-working day,
    snap forward to the start of the next valid working window (09:30 IST).
    If dt is during working hours on a working day, returns dt unchanged.
    """
    dt_ist = to_ist(dt)
    d = dt_ist.date()
    t = dt_ist.time()

    # Check non-working day
    if not is_working_day(d, holidays):
        nxt = next_working_day(d, holidays)
        return datetime.combine(nxt, START_TIME, tzinfo=IST)

    # Working day, before start
    if t < START_TIME:
        return datetime.combine(d, START_TIME, tzinfo=IST)

    # Working day, after end
    if t >= END_TIME:
        nxt = next_working_day(d, holidays)
        return datetime.combine(nxt, START_TIME, tzinfo=IST)

    # Inside working window
    return dt_ist

def end_of_working_day(dt: datetime, holidays: Set[date]) -> datetime:
    """
    If dt is outside working hours or on a non-working day,
    snap forward to next working day start, then return 18:30 of that working day.
    """
    effective_start = snap_to_working_window(dt, holidays)
    d = effective_start.date()
    return datetime.combine(d, END_TIME, tzinfo=IST)

def add_working_minutes(start_dt: datetime, minutes: int, holidays: Set[date]) -> datetime:
    """
    Add specified working minutes to start_dt considering IST working window:
    Monday-Friday 09:30-18:30 IST, skipping weekends and holidays.
    """
    if minutes <= 0:
        return snap_to_working_window(start_dt, holidays)

    curr = snap_to_working_window(start_dt, holidays)
    remaining = minutes

    while remaining > 0:
        d = curr.date()
        day_end = datetime.combine(d, END_TIME, tzinfo=IST)
        mins_left_today = int((day_end - curr).total_seconds() // 60)

        if remaining <= mins_left_today:
            curr = curr + timedelta(minutes=remaining)
            remaining = 0
            break
        else:
            remaining -= mins_left_today
            nxt = next_working_day(d, holidays)
            curr = datetime.combine(nxt, START_TIME, tzinfo=IST)

    return curr

def working_minutes_between(start_dt: datetime, end_dt: datetime, holidays: Set[date]) -> int:
    """
    Calculate the total working minutes elapsed between start_dt and end_dt.
    If end_dt <= start_dt, returns 0.
    """
    if end_dt <= start_dt:
        return 0

    s = to_ist(start_dt)
    e = to_ist(end_dt)

    if e <= s:
        return 0

    curr = s
    total_mins = 0

    while curr.date() <= e.date():
        d = curr.date()
        if is_working_day(d, holidays):
            window_start = datetime.combine(d, START_TIME, tzinfo=IST)
            window_end = datetime.combine(d, END_TIME, tzinfo=IST)

            interval_start = max(curr, window_start)
            interval_end = min(e, window_end)

            if interval_end > interval_start:
                total_mins += int((interval_end - interval_start).total_seconds() // 60)

        # Move to next calendar day at midnight
        next_date = d + timedelta(days=1)
        curr = datetime.combine(next_date, time(0, 0), tzinfo=IST)

    return total_mins

def calculate_initial_sla_deadlines(
    created_at: datetime,
    priority: str,
    holidays: Set[date]
) -> Tuple[datetime, datetime]:
    """
    Calculate (first_response_due_at, resolution_due_at) for a newly created ticket.
    """
    eff_start = snap_to_working_window(created_at, holidays)

    if priority == "URGENT":
        first_resp_due = add_working_minutes(eff_start, 120, holidays)
        same_day_end = end_of_working_day(eff_start, holidays)
        min_resolution = add_working_minutes(eff_start, 120, holidays)
        resol_due = max(same_day_end, min_resolution)
    elif priority == "MEDIUM":
        first_resp_due = add_working_minutes(eff_start, 270, holidays)
        resol_due = add_working_minutes(eff_start, 1620, holidays)
    else:  # LOW
        first_resp_due = add_working_minutes(eff_start, 540, holidays)
        resol_due = add_working_minutes(eff_start, 2700, holidays)

    return first_resp_due, resol_due

def recalculate_sla_on_escalation(
    created_at: datetime,
    new_priority: str,
    total_paused_working_minutes: int,
    first_responded_at: Optional[datetime],
    holidays: Set[date]
) -> Tuple[Optional[datetime], datetime]:
    """
    Recalculate first_response_due_at (if not yet responded) and resolution_due_at
    from created_at using the new priority's working-time budget plus total_paused_working_minutes.
    """
    eff_start = snap_to_working_window(created_at, holidays)

    if new_priority == "URGENT":
        resp_budget = 120
        same_day_end = end_of_working_day(eff_start, holidays)
        min_resolution = add_working_minutes(eff_start, 120 + total_paused_working_minutes, holidays)
        resol_base = max(same_day_end, add_working_minutes(eff_start, 120, holidays))
        resol_due = add_working_minutes(resol_base, total_paused_working_minutes, holidays)
    elif new_priority == "MEDIUM":
        resp_budget = 270
        resol_budget = 1620
        resol_due = add_working_minutes(eff_start, resol_budget + total_paused_working_minutes, holidays)
    else:  # LOW
        resp_budget = 540
        resol_budget = 2700
        resol_due = add_working_minutes(eff_start, resol_budget + total_paused_working_minutes, holidays)

    if first_responded_at is None:
        first_resp_due = add_working_minutes(eff_start, resp_budget + total_paused_working_minutes, holidays)
    else:
        first_resp_due = None

    return first_resp_due, resol_due
