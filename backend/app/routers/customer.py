import csv
import io
import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import (
    User, UserRole, Ticket, TicketStatus, PublicMessage, AuditAction
)
from app.models.schemas import (
    CustomerTicketItem, CustomerTicketDetail, CustomerTicketCreate,
    PublicMessageCreate, PublicMessageOut, TicketReopenResponse
)
from app.services.ticket_service import (
    get_holiday_dates, log_audit_event, resume_sla_if_paused,
    handle_customer_reopen_or_followup
)
from app.services.sla import (
    IST, to_ist, to_utc, calculate_initial_sla_deadlines
)

router = APIRouter(prefix="/api/customer", tags=["Customer Portal — STRICT ZERO-LEAK ZONE"])

def get_current_customer(customer_id: int, db: Session) -> User:
    customer = db.query(User).filter(User.id == customer_id, User.role == UserRole.CUSTOMER).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@router.get("/tickets", response_model=List[CustomerTicketItem])
def list_customer_tickets(
    customer_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    List customer's tickets.
    INC-0304: Zero internal notes, zero agent-only metrics.
    """
    get_current_customer(customer_id, db)
    tickets = db.query(Ticket).filter(Ticket.customer_id == customer_id).order_by(Ticket.created_at.desc()).all()
    return tickets

@router.get("/tickets/{id}", response_model=CustomerTicketDetail)
def get_customer_ticket(
    id: int,
    customer_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    Returns ticket + public_messages ONLY.
    INC-0304: Strictly zero internal notes and separated Pydantic response schema.
    """
    customer = get_current_customer(customer_id, db)
    ticket = db.query(Ticket).filter(Ticket.id == id, Ticket.customer_id == customer.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found for this customer")

    pub_msgs = [
        PublicMessageOut(
            id=m.id,
            ticket_id=m.ticket_id,
            author_id=m.author_id,
            author_role=m.author_role,
            author_name=m.author.name if m.author else None,
            body=m.body,
            created_at=m.created_at
        )
        for m in ticket.public_messages
    ]

    return CustomerTicketDetail(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        subject=ticket.subject,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        first_responded_at=ticket.first_responded_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        parent_ticket_id=ticket.parent_ticket_id,
        public_messages=pub_msgs
    )

@router.post("/tickets", response_model=CustomerTicketDetail)
def create_customer_ticket(
    payload: CustomerTicketCreate,
    customer_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """Customer creates a new ticket."""
    customer = get_current_customer(customer_id, db)
    holidays = get_holiday_dates(db)
    now = datetime.now(timezone.utc)

    last_id = db.query(Ticket.id).order_by(Ticket.id.desc()).first()
    next_num = (last_id[0] + 1001) if last_id else 1001
    ticket_num = f"FD-{next_num}"

    f_due, r_due = calculate_initial_sla_deadlines(to_ist(now), payload.priority.value, holidays)

    ticket = Ticket(
        ticket_number=ticket_num,
        subject=payload.subject,
        description=payload.description,
        customer_id=customer.id,
        assignee_id=None,
        priority=payload.priority,
        status=TicketStatus.OPEN,
        created_at=now,
        updated_at=now,
        first_response_due_at=to_utc(f_due),
        resolution_due_at=to_utc(r_due),
    )
    db.add(ticket)
    db.flush()

    # Initial public message recording customer's description
    msg = PublicMessage(
        ticket_id=ticket.id,
        author_id=customer.id,
        author_role=UserRole.CUSTOMER,
        body=payload.description,
        created_at=now
    )
    db.add(msg)

    log_audit_event(
        db,
        ticket_id=ticket.id,
        action=AuditAction.TICKET_CREATED,
        actor_id=customer.id,
        actor_name=customer.name,
        metadata={"priority": payload.priority.value, "by": "customer"}
    )
    db.commit()
    db.refresh(ticket)
    return get_customer_ticket(ticket.id, customer.id, db)

@router.post("/tickets/{id}/reply", response_model=CustomerTicketDetail)
def customer_reply(
    id: int,
    payload: PublicMessageCreate,
    customer_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    Customer replies.
    Automatically resumes paused SLA if ticket was in WAITING_ON_CUSTOMER!
    """
    customer = get_current_customer(customer_id, db)
    ticket = db.query(Ticket).filter(Ticket.id == id, Ticket.customer_id == customer.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    holidays = get_holiday_dates(db)

    # Add message
    msg = PublicMessage(
        ticket_id=ticket.id,
        author_id=customer.id,
        author_role=UserRole.CUSTOMER,
        body=payload.body,
        created_at=now
    )
    db.add(msg)

    log_audit_event(
        db,
        ticket_id=ticket.id,
        action=AuditAction.CUSTOMER_REPLIED,
        actor_id=customer.id,
        actor_name=customer.name,
        metadata={}
    )

    # Check SLA resume
    if ticket.status == TicketStatus.WAITING_ON_CUSTOMER:
        paused_mins = resume_sla_if_paused(ticket, holidays, now)
        ticket.status = TicketStatus.IN_PROGRESS
        log_audit_event(
            db,
            ticket_id=ticket.id,
            action=AuditAction.SLA_RESUMED,
            actor_id=customer.id,
            actor_name=customer.name,
            metadata={"resumed_on": "CUSTOMER_REPLY", "added_paused_working_minutes": paused_mins}
        )

    ticket.updated_at = now
    db.commit()
    db.refresh(ticket)
    return get_customer_ticket(ticket.id, customer.id, db)

@router.post("/tickets/{id}/reopen", response_model=TicketReopenResponse)
def customer_reopen(
    id: int,
    customer_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    Reopens ticket if within 1 working week of resolved_at;
    Otherwise creates a new linked ticket and returns reopened: false, new_ticket_id: ...
    """
    customer = get_current_customer(customer_id, db)
    ticket = db.query(Ticket).filter(Ticket.id == id, Ticket.customer_id == customer.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        return TicketReopenResponse(
            reopened=True,
            ticket_id=ticket.id,
            ticket_number=ticket.ticket_number,
            message="Ticket is already active."
        )

    holidays = get_holiday_dates(db)
    reopened, target_ticket = handle_customer_reopen_or_followup(db, ticket, customer, holidays)

    if reopened:
        return TicketReopenResponse(
            reopened=True,
            ticket_id=target_ticket.id,
            ticket_number=target_ticket.ticket_number,
            message=f"Ticket {target_ticket.ticket_number} has been reopened successfully."
        )
    else:
        return TicketReopenResponse(
            reopened=False,
            ticket_id=target_ticket.id,
            ticket_number=target_ticket.ticket_number,
            message=f"Reopen window expired (> 1 working week). Follow-up ticket {target_ticket.ticket_number} was created."
        )

@router.get("/tickets/{id}/export")
def export_customer_ticket(
    id: int,
    customer_id: int = Query(...),
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db)
):
    """
    INC-0304: Zero-Leak Internal Team Notes.
    JSON/CSV export of customer conversation (EXPLICITLY EXCLUDES internal_notes).
    """
    customer = get_current_customer(customer_id, db)
    ticket = db.query(Ticket).filter(Ticket.id == id, Ticket.customer_id == customer.id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Only public messages
    messages_data = [
        {
            "id": m.id,
            "author_name": m.author.name if m.author else "Unknown",
            "author_role": m.author_role.value,
            "body": m.body,
            "created_at": m.created_at.isoformat()
        }
        for m in ticket.public_messages
    ]

    export_payload = {
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "description": ticket.description,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "created_at": ticket.created_at.isoformat(),
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "conversation": messages_data
    }

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Message ID", "Author Name", "Author Role", "Created At (UTC)", "Message Body"])
        # Initial description
        writer.writerow(["0", customer.name, "CUSTOMER", ticket.created_at.isoformat(), ticket.description])
        for m in messages_data:
            writer.writerow([m["id"], m["author_name"], m["author_role"], m["created_at"], m["body"]])
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={ticket.ticket_number}_export.csv"}
        )

    return Response(
        content=json.dumps(export_payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={ticket.ticket_number}_export.json"}
    )
