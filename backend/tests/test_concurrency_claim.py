"""
INC-0291 — Atomic Ticket Claiming Test (Zero Double-Claiming)
Two agents must NEVER be able to claim the same unassigned ticket simultaneously.
Assert that the conditional DB update succeeds for the first agent and raises HTTP 409 Conflict for any subsequent attempt.
"""

import uuid
import pytest
from fastapi import HTTPException
from app.database import SessionLocal
from app.models.models import User, Ticket, TicketStatus
from app.services.ticket_service import atomic_claim_ticket

def test_atomic_ticket_claim_concurrency():
    db1 = SessionLocal()
    db2 = SessionLocal()

    try:
        unique_num = f"FD-TEST-{uuid.uuid4().hex[:6]}"
        # Create an unassigned test ticket
        t = Ticket(
            ticket_number=unique_num,
            subject="Concurrency Test Ticket",
            description="Testing atomic conditional update",
            customer_id=10,
            assignee_id=None,
            status=TicketStatus.OPEN
        )
        db1.add(t)
        db1.commit()
        db1.refresh(t)

        agent1 = db1.query(User).filter(User.id == 2).first() # Aarav
        agent2 = db2.query(User).filter(User.id == 3).first() # Pooja

        # First claim succeeds
        claimed_ticket = atomic_claim_ticket(db1, t.id, agent1)
        assert claimed_ticket.assignee_id == agent1.id
        assert claimed_ticket.status == TicketStatus.IN_PROGRESS

        # Second claim attempt on the same ticket MUST raise 409 Conflict
        with pytest.raises(HTTPException) as exc_info:
            atomic_claim_ticket(db2, t.id, agent2)

        assert exc_info.value.status_code == 409
        assert "Conflict" in exc_info.value.detail
        assert "already been claimed by" in exc_info.value.detail
        assert agent1.name in exc_info.value.detail

    finally:
        db1.close()
        db2.close()
