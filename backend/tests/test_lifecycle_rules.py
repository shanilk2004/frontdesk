"""
Lifecycle rules tests:
- Auto-close after 5 working days of waiting on customer
- Reopen within 1 working week
- New-ticket creation after 1 working week
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from app.database import SessionLocal
from app.models.models import Ticket, TicketStatus, User, TicketPriority
from app.routers import admin, customer
from app.services.ticket_service import get_holiday_dates, run_auto_close_inactivity_check

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

def test_auto_close_inactivity(db):
    holidays = get_holiday_dates(db)
    now = datetime.now(timezone.utc)
    eight_days_ago = now - timedelta(days=8)

    # Create dedicated ticket waiting for 8 calendar days
    t = Ticket(
        ticket_number=f"FD-AC-{uuid.uuid4().hex[:6]}",
        subject="Auto-Close Inactivity Test Ticket",
        description="Testing auto-close after 5 working days of waiting",
        customer_id=10,
        assignee_id=1,
        priority=TicketPriority.LOW,
        status=TicketStatus.WAITING_ON_CUSTOMER,
        created_at=eight_days_ago - timedelta(days=1),
        updated_at=eight_days_ago,
        sla_paused_at=eight_days_ago
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    closed_ids = run_auto_close_inactivity_check(db, holidays, now)
    assert t.id in closed_ids

    # Verify status changed to CLOSED
    db.refresh(t)
    assert t.status == TicketStatus.CLOSED

def test_reopen_within_one_week(db):
    now = datetime.now(timezone.utc)
    # Create ticket resolved 2 days ago
    t = Ticket(
        ticket_number=f"FD-RO-{uuid.uuid4().hex[:6]}",
        subject="Reopen Window Test Ticket",
        description="Testing reopen within 1 week",
        customer_id=10,
        assignee_id=1,
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.RESOLVED,
        created_at=now - timedelta(days=4),
        updated_at=now - timedelta(days=2),
        resolved_at=now - timedelta(days=2)
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    res = customer.customer_reopen(id=t.id, customer_id=t.customer_id, db=db)
    assert res.reopened is True
    assert res.ticket_id == t.id

    # Verify status in DB is IN_PROGRESS
    db.refresh(t)
    assert t.status == TicketStatus.IN_PROGRESS

def test_followup_ticket_after_reopen_window_expired(db):
    now = datetime.now(timezone.utc)
    # Create ticket resolved 14 days ago (> 1 working week)
    t = Ticket(
        ticket_number=f"FD-FO-{uuid.uuid4().hex[:6]}",
        subject="Follow-up Window Expired Ticket",
        description="Testing follow-up ticket generation",
        customer_id=10,
        assignee_id=1,
        priority=TicketPriority.LOW,
        status=TicketStatus.RESOLVED,
        created_at=now - timedelta(days=20),
        updated_at=now - timedelta(days=14),
        resolved_at=now - timedelta(days=14)
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    res = customer.customer_reopen(id=t.id, customer_id=t.customer_id, db=db)
    assert res.reopened is False
    assert res.ticket_id != t.id

    # Original ticket remains RESOLVED
    db.refresh(t)
    assert t.status == TicketStatus.RESOLVED

    # New ticket has parent_ticket_id = t.id
    new_t = db.query(Ticket).filter(Ticket.id == res.ticket_id).first()
    assert new_t is not None
    assert new_t.parent_ticket_id == t.id
    assert "[Follow-up]" in new_t.subject
