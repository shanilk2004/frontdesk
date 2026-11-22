from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.dependencies import require_agent
from app.models.models import (
    User, UserRole, Ticket, TicketPriority, TicketStatus,
    PublicMessage, InternalNote, AuditLog, AuditAction
)
from app.models.schemas import (
    UserOut, AgentTicketItem, AgentTicketDetail, TicketCreate,
    TicketReplyRequest, InternalNoteCreate, InternalNoteOut,
    TicketUpdateRequest, AuditLogOut, PublicMessageOut
)
from app.services.ticket_service import (
    get_holiday_dates, compute_ticket_sla_status, log_audit_event,
    atomic_claim_ticket, resume_sla_if_paused
)
from app.services.sla import (
    IST, to_ist, to_utc, calculate_initial_sla_deadlines,
    recalculate_sla_on_escalation
)

router = APIRouter(prefix="/api/agent", tags=["Agent Operations"])

@router.get("/agents", response_model=List[UserOut])
def list_agents(db: Session = Depends(get_db)):
    """List all 9 Arvo support agents and leads."""
    return db.query(User).filter(User.role.in_([UserRole.AGENT, UserRole.LEAD])).all()

@router.get("/tickets", response_model=List[AgentTicketItem])
def list_agent_tickets(
    status_filter: Optional[TicketStatus] = Query(None, alias="status"),
    priority_filter: Optional[TicketPriority] = Query(None, alias="priority"),
    assignee_id: Optional[int] = Query(None),
    unassigned: Optional[bool] = Query(None),
    breached_only: Optional[bool] = Query(None),
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """
    List tickets with computed SLA state (is_breached, breach_type, remaining_working_minutes, is_paused).
    Sort breached & urgent tickets first.
    """
    holidays = get_holiday_dates(db)
    query = db.query(Ticket)

    if status_filter:
        query = query.filter(Ticket.status == status_filter)
    if priority_filter:
        query = query.filter(Ticket.priority == priority_filter)
    if assignee_id is not None:
        query = query.filter(Ticket.assignee_id == assignee_id)
    if unassigned is True:
        query = query.filter(Ticket.assignee_id.is_(None))

    tickets = query.all()
    results = []

    for t in tickets:
        sla_stat = compute_ticket_sla_status(t, holidays)
        if breached_only and not sla_stat.is_breached:
            continue

        item = AgentTicketItem(
            id=t.id,
            ticket_number=t.ticket_number,
            subject=t.subject,
            description=t.description,
            status=t.status,
            priority=t.priority,
            customer_id=t.customer_id,
            customer_name=t.customer.name if t.customer else None,
            customer_email=t.customer.email if t.customer else None,
            assignee_id=t.assignee_id,
            assignee_name=t.assignee.name if t.assignee else None,
            created_at=t.created_at,
            updated_at=t.updated_at,
            first_responded_at=t.first_responded_at,
            resolved_at=t.resolved_at,
            closed_at=t.closed_at,
            first_response_due_at=t.first_response_due_at,
            resolution_due_at=t.resolution_due_at,
            sla_paused_at=t.sla_paused_at,
            total_paused_working_minutes=t.total_paused_working_minutes,
            parent_ticket_id=t.parent_ticket_id,
            sla=sla_stat
        )
        results.append(item)

    # Sort priority: Breached first, then by priority (URGENT -> MEDIUM -> LOW), then created_at desc
    priority_order = {TicketPriority.URGENT: 0, TicketPriority.MEDIUM: 1, TicketPriority.LOW: 2}
    results.sort(key=lambda x: (
        0 if (x.sla and x.sla.is_breached) else 1,
        priority_order.get(x.priority, 3),
        -x.created_at.timestamp()
    ))

    return results

@router.post("/tickets", response_model=AgentTicketDetail)
def create_agent_ticket(
    payload: TicketCreate,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """Create a ticket on behalf of a customer."""
    customer = db.query(User).filter(User.id == payload.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

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

    log_audit_event(
        db,
        ticket_id=ticket.id,
        action=AuditAction.TICKET_CREATED,
        actor_id=agent.id,
        actor_name=f"{agent.name} (on behalf of customer)",
        metadata={"priority": payload.priority.value, "customer_id": customer.id}
    )
    db.commit()
    db.refresh(ticket)
    return get_agent_ticket_detail(ticket.id, agent, db)

@router.get("/tickets/{id}", response_model=AgentTicketDetail)
def get_agent_ticket_detail(
    id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """Full ticket detail including public_messages, internal_notes, and audit_logs."""
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    holidays = get_holiday_dates(db)
    sla_stat = compute_ticket_sla_status(ticket, holidays)

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

    int_notes = [
        InternalNoteOut(
            id=n.id,
            ticket_id=n.ticket_id,
            author_id=n.author_id,
            author_name=n.author.name if n.author else None,
            body=n.body,
            created_at=n.created_at
        )
        for n in ticket.internal_notes
    ]

    audit_items = [
        AuditLogOut(
            id=a.id,
            ticket_id=a.ticket_id,
            actor_id=a.actor_id,
            actor_name=a.actor_name,
            action=a.action,
            metadata=a.meta,
            created_at=a.created_at
        )
        for a in ticket.audit_logs
    ]

    return AgentTicketDetail(
        id=ticket.id,
        ticket_number=ticket.ticket_number,
        subject=ticket.subject,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        customer_id=ticket.customer_id,
        customer_name=ticket.customer.name if ticket.customer else None,
        customer_email=ticket.customer.email if ticket.customer else None,
        assignee_id=ticket.assignee_id,
        assignee_name=ticket.assignee.name if ticket.assignee else None,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        first_responded_at=ticket.first_responded_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
        first_response_due_at=ticket.first_response_due_at,
        resolution_due_at=ticket.resolution_due_at,
        sla_paused_at=ticket.sla_paused_at,
        total_paused_working_minutes=ticket.total_paused_working_minutes,
        parent_ticket_id=ticket.parent_ticket_id,
        sla=sla_stat,
        public_messages=pub_msgs,
        internal_notes=int_notes,
        audit_logs=audit_items
    )

@router.post("/tickets/{id}/claim", response_model=AgentTicketDetail)
def claim_ticket(
    id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """Atomic claim (INC-0291). Returns 409 Conflict if already claimed."""
    atomic_claim_ticket(db, id, agent)
    return get_agent_ticket_detail(id, agent, db)

@router.post("/tickets/{id}/reply", response_model=AgentTicketDetail)
def reply_ticket(
    id: int,
    payload: TicketReplyRequest,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """
    Send public reply to customer; optional wait_for_customer flag to immediately
    pause SLA and set status to WAITING_ON_CUSTOMER.
    Sets first_responded_at if first agent reply.
    """
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    holidays = get_holiday_dates(db)

    # First responded check
    is_first_response = False
    if ticket.first_responded_at is None:
        ticket.first_responded_at = now
        is_first_response = True

    msg = PublicMessage(
        ticket_id=ticket.id,
        author_id=agent.id,
        author_role=agent.role,
        body=payload.body,
        created_at=now
    )
    db.add(msg)

    log_audit_event(
        db,
        ticket_id=ticket.id,
        action=AuditAction.PUBLIC_REPLY_SENT,
        actor_id=agent.id,
        actor_name=agent.name,
        metadata={"is_first_response": is_first_response, "wait_for_customer": payload.wait_for_customer}
    )

    if payload.wait_for_customer:
        old_status = ticket.status
        ticket.status = TicketStatus.WAITING_ON_CUSTOMER
        ticket.sla_paused_at = now
        log_audit_event(
            db,
            ticket_id=ticket.id,
            action=AuditAction.SLA_PAUSED,
            actor_id=agent.id,
            actor_name=agent.name,
            metadata={"from_status": old_status.value, "to_status": "WAITING_ON_CUSTOMER"}
        )
    elif ticket.status == TicketStatus.OPEN:
        ticket.status = TicketStatus.IN_PROGRESS

    ticket.updated_at = now
    db.commit()
    db.refresh(ticket)
    return get_agent_ticket_detail(id, agent, db)

@router.post("/tickets/{id}/notes", response_model=InternalNoteOut)
def add_internal_note(
    id: int,
    payload: InternalNoteCreate,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """Add private team-only note to internal_notes (INC-0304)."""
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    note = InternalNote(
        ticket_id=ticket.id,
        author_id=agent.id,
        body=payload.body,
        created_at=now
    )
    db.add(note)
    db.flush()

    log_audit_event(
        db,
        ticket_id=ticket.id,
        action=AuditAction.INTERNAL_NOTE_ADDED,
        actor_id=agent.id,
        actor_name=agent.name,
        metadata={"note_id": note.id}
    )
    ticket.updated_at = now
    db.commit()
    db.refresh(note)

    return InternalNoteOut(
        id=note.id,
        ticket_id=note.ticket_id,
        author_id=note.author_id,
        author_name=agent.name,
        body=note.body,
        created_at=note.created_at
    )

@router.patch("/tickets/{id}", response_model=AgentTicketDetail)
def update_ticket(
    id: int,
    payload: TicketUpdateRequest,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """Update status (handle pause/resume/resolve) or priority (handle SLA recalculation)."""
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    now = datetime.now(timezone.utc)
    holidays = get_holiday_dates(db)

    # 1. Priority Change (Escalation / De-escalation)
    if payload.priority and payload.priority != ticket.priority:
        old_priority = ticket.priority
        new_priority = payload.priority
        old_f_due = ticket.first_response_due_at
        old_r_due = ticket.resolution_due_at

        # Recalculate SLA deadlines
        new_f_due, new_r_due = recalculate_sla_on_escalation(
            created_at=to_ist(ticket.created_at),
            new_priority=new_priority.value,
            total_paused_working_minutes=ticket.total_paused_working_minutes,
            first_responded_at=to_ist(ticket.first_responded_at) if ticket.first_responded_at else None,
            holidays=holidays
        )

        ticket.priority = new_priority
        if new_f_due:
            ticket.first_response_due_at = to_utc(new_f_due)
        ticket.resolution_due_at = to_utc(new_r_due)

        log_audit_event(
            db,
            ticket_id=ticket.id,
            action=AuditAction.PRIORITY_CHANGED,
            actor_id=agent.id,
            actor_name=agent.name,
            metadata={
                "old_priority": old_priority.value,
                "new_priority": new_priority.value,
                "old_first_response_due": old_f_due.isoformat() if old_f_due else None,
                "new_first_response_due": ticket.first_response_due_at.isoformat() if ticket.first_response_due_at else None,
                "old_resolution_due": old_r_due.isoformat() if old_r_due else None,
                "new_resolution_due": ticket.resolution_due_at.isoformat() if ticket.resolution_due_at else None,
            }
        )

    # 2. Status Change
    if payload.status and payload.status != ticket.status:
        old_status = ticket.status
        new_status = payload.status

        # Transitioning TO WAITING_ON_CUSTOMER -> Pause SLA
        if new_status == TicketStatus.WAITING_ON_CUSTOMER:
            ticket.sla_paused_at = now
            log_audit_event(
                db,
                ticket_id=ticket.id,
                action=AuditAction.SLA_PAUSED,
                actor_id=agent.id,
                actor_name=agent.name,
                metadata={"from_status": old_status.value, "to_status": new_status.value}
            )

        # Transitioning FROM WAITING_ON_CUSTOMER -> Resume SLA
        if old_status == TicketStatus.WAITING_ON_CUSTOMER and new_status != TicketStatus.WAITING_ON_CUSTOMER:
            paused_mins = resume_sla_if_paused(ticket, holidays, now)
            log_audit_event(
                db,
                ticket_id=ticket.id,
                action=AuditAction.SLA_RESUMED,
                actor_id=agent.id,
                actor_name=agent.name,
                metadata={"resumed_to": new_status.value, "added_paused_working_minutes": paused_mins}
            )

        # Transitioning TO RESOLVED
        if new_status == TicketStatus.RESOLVED:
            ticket.resolved_at = now
            log_audit_event(
                db,
                ticket_id=ticket.id,
                action=AuditAction.TICKET_RESOLVED,
                actor_id=agent.id,
                actor_name=agent.name,
                metadata={}
            )

        # Transitioning TO CLOSED
        if new_status == TicketStatus.CLOSED:
            ticket.closed_at = now

        ticket.status = new_status
        log_audit_event(
            db,
            ticket_id=ticket.id,
            action=AuditAction.STATUS_CHANGED,
            actor_id=agent.id,
            actor_name=agent.name,
            metadata={"old_status": old_status.value, "new_status": new_status.value}
        )

    ticket.updated_at = now
    db.commit()
    db.refresh(ticket)
    return get_agent_ticket_detail(id, agent, db)

@router.get("/tickets/{id}/audit", response_model=List[AuditLogOut])
def get_ticket_audit_trail(
    id: int,
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db)
):
    """Fetch immutable audit trail."""
    ticket = db.query(Ticket).filter(Ticket.id == id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    logs = db.query(AuditLog).filter(AuditLog.ticket_id == id).order_by(AuditLog.created_at.asc()).all()
    return [
        AuditLogOut(
            id=l.id,
            ticket_id=l.ticket_id,
            actor_id=l.actor_id,
            actor_name=l.actor_name,
            action=l.action,
            metadata=l.meta,
            created_at=l.created_at
        )
        for l in logs
    ]
