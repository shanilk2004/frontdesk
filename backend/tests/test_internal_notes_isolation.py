"""
Direct unit and integration tests for route handlers and services.
Executes synchronously with zero event loop or thread hang risks.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.database import SessionLocal
from app.models.models import User, UserRole, Ticket, TicketStatus, TicketPriority
from app.models.schemas import (
    TicketReplyRequest, InternalNoteCreate, TicketUpdateRequest,
    CustomerTicketCreate, PublicMessageCreate
)
from app.routers import agent, customer, admin
from app.services.ticket_service import atomic_claim_ticket, run_auto_close_inactivity_check

@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()

def test_internal_notes_isolation(db):
    SECRET_STRING = "SUPER_SECRET_INTERNAL_TOKEN_XYZ999"
    # Agent 1 (Meera)
    meera = db.query(User).filter(User.id == 1).first()
    ticket = db.query(Ticket).filter(Ticket.id == 1).first()

    # Agent adds note
    note_resp = agent.add_internal_note(
        id=ticket.id,
        payload=InternalNoteCreate(body=f"Confidential note: {SECRET_STRING}"),
        agent=meera,
        db=db
    )
    assert note_resp.id is not None

    # Agent view has it
    agent_ticket = agent.get_agent_ticket_detail(id=ticket.id, agent=meera, db=db)
    agent_note_bodies = [n.body for n in agent_ticket.internal_notes]
    assert any(SECRET_STRING in b for b in agent_note_bodies)

    # Customer view DOES NOT have internal_notes attribute or secret
    cust_ticket = customer.get_customer_ticket(id=ticket.id, customer_id=ticket.customer_id, db=db)
    assert not hasattr(cust_ticket, "internal_notes")
    # Check public messages
    cust_msg_bodies = [m.body for m in cust_ticket.public_messages]
    assert not any(SECRET_STRING in b for b in cust_msg_bodies)

    # Export also excludes it
    export_resp = customer.export_customer_ticket(id=ticket.id, customer_id=ticket.customer_id, format="json", db=db)
    assert SECRET_STRING not in export_resp.body.decode("utf-8")
