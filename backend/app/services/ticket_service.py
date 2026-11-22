"""
Ticket Service handling lifecycle rules, atomic claiming, SLA updates,
and audit logging.
"""

from datetime import datetime, timezone, timedelta, date
from typing import Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.models.models import (
    User, UserRole, Ticket, TicketPriority, TicketStatus,
    PublicMessage, InternalNote, AuditLog, Holiday, AuditAction
)
from app.models.schemas import TicketSLAStatus
from app.services.sla import (
    IST, UTC, to_ist, to_utc, calculate_initial_sla_deadlines,
    recalculate_sla_on_escalation, working_minutes_between, snap_to_working_window
)

def get_holiday_dates(db: Session) -> Set[date]:
    return {h.date for h in db.query(Holiday.date).all()}

def compute_ticket_sla_status(ticket: Ticket, holidays: Set[date], as_of: Optional[datetime] = None) -> TicketSLAStatus:
    now_utc = as_of if as_of else datetime.now(timezone.utc)
    now_ist = to_ist(now_utc)

    is_paused = ticket.status == TicketStatus.WAITING_ON_CUSTOMER
    is_breached = False
    breach_type = None
    remaining_resp = None
    remaining_resol = None

    # First response evaluation
    if ticket.first_response_due_at:
        f_due_ist = to_ist(ticket.first_response_due_at)
        if ticket.first_responded_at:
            # Responded already: compare response time with due time
            resp_ist = to_ist(ticket.first_responded_at)
            if resp_ist > f_due_ist:
                is_breached = True
                breach_type = "FIRST_RESPONSE_BREACHED"
        else:
            # Not yet responded
            if not is_paused and now_ist > f_due_ist:
                is_breached = True
                breach_type = "FIRST_RESPONSE_BREACHED"
            elif not is_paused:
                remaining_resp = working_minutes_between(now_ist, f_due_ist, holidays)

    # Resolution evaluation
    if ticket.resolution_due_at:
        r_due_ist = to_ist(ticket.resolution_due_at)
        if ticket.resolved_at:
            resol_ist = to_ist(ticket.resolved_at)
            if resol_ist > r_due_ist:
                is_breached = True
                breach_type = "BOTH" if breach_type else "RESOLUTION_BREACHED"
        elif ticket.status not in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
            if not is_paused and now_ist > r_due_ist:
                is_breached = True
                breach_type = "BOTH" if breach_type else "RESOLUTION_BREACHED"
            elif not is_paused:
                remaining_resol = working_minutes_between(now_ist, r_due_ist, holidays)

    return TicketSLAStatus(
        is_breached=is_breached,
        breach_type=breach_type,
        is_paused=is_paused,
        remaining_response_minutes=remaining_resp,
        remaining_resolution_minutes=remaining_resol,
        first_response_due_at=ticket.first_response_due_at,
        resolution_due_at=ticket.resolution_due_at,
        total_paused_working_minutes=ticket.total_paused_working_minutes,
    )

def log_audit_event(
    db: Session,
    ticket_id: int,
    action: str,
    actor_id: Optional[int] = None,
    actor_name: str = "System",
    metadata: Optional[dict] = None,
    created_at: Optional[datetime] = None
) -> AuditLog:
    entry = AuditLog(
        ticket_id=ticket_id,
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        meta=metadata or {},
        created_at=created_at or datetime.now(timezone.utc)
    )
    db.add(entry)
    return entry

def atomic_claim_ticket(db: Session, ticket_id: int, agent: User) -> Ticket:
    """
    INC-0291 — Atomic Ticket Claiming (Zero Double-Claiming)
    Two agents must NEVER be able to claim the same unassigned ticket simultaneously.
    Enforce at DB level with atomic conditional UPDATE:
    UPDATE tickets SET assignee_id = :agent_id, status = 'IN_PROGRESS', updated_at = NOW()
    WHERE id = :ticket_id AND assignee_id IS NULL;
    """
    now = datetime.now(timezone.utc)
    
    # Check dialect for returning support
    dialect = db.bind.dialect.name
    if dialect in ("postgresql", "sqlite"):
        stmt = text("""
            UPDATE tickets
            SET assignee_id = :agent_id, status = 'IN_PROGRESS', updated_at = :now
            WHERE id = :ticket_id AND assignee_id IS NULL
        """)
        result = db.execute(stmt, {"agent_id": agent.id, "ticket_id": ticket_id, "now": now})
        db.commit()

        if result.rowcount == 0:
            # 0 rows returned: already claimed by another agent
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                raise HTTPException(status_code=404, detail="Ticket not found")
            
            holder_name = ticket.assignee.name if ticket.assignee else "another agent"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Conflict: Ticket {ticket.ticket_number} has already been claimed by {holder_name}."
            )
    else:
        # Generic fallback
        pass

    # Retrieve updated ticket
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    log_audit_event(
        db,
        ticket_id=ticket.id,
        action=AuditAction.TICKET_CLAIMED,
        actor_id=agent.id,
        actor_name=agent.name,
        metadata={"assignee_id": agent.id, "assignee_name": agent.name}
    )
    db.commit()
    db.refresh(ticket)
    return ticket

def resume_sla_if_paused(ticket: Ticket, holidays: Set[date], now_utc: datetime) -> int:
    """
    When customer replies or agent resumes:
    Calculate paused_working_mins = working_minutes_between(sla_paused_at, NOW(), holidays)
    Add it to total_paused_working_minutes, clear sla_paused_at,
    and shift resolution_due_at (and first_response_due_at if still unanswered) forward.
    """
    if not ticket.sla_paused_at:
        return 0

    paused_at_ist = to_ist(ticket.sla_paused_at)
    now_ist = to_ist(now_utc)
    paused_working_mins = working_minutes_between(paused_at_ist, now_ist, holidays)

    ticket.total_paused_working_minutes += paused_working_mins
    ticket.sla_paused_at = None

    if paused_working_mins > 0:
        from app.services.sla import add_working_minutes
        if ticket.resolution_due_at:
            r_ist = to_ist(ticket.resolution_due_at)
            ticket.resolution_due_at = to_utc(add_working_minutes(r_ist, paused_working_mins, holidays))
        if ticket.first_response_due_at and not ticket.first_responded_at:
            f_ist = to_ist(ticket.first_response_due_at)
            ticket.first_response_due_at = to_utc(add_working_minutes(f_ist, paused_working_mins, holidays))

    return paused_working_mins

def handle_customer_reopen_or_followup(
    db: Session,
    ticket: Ticket,
    customer: User,
    holidays: Set[date],
    now_utc: Optional[datetime] = None
) -> Tuple[bool, Ticket]:
    """
    Reopen Window: 1 working week (5 working days = 2,700 working minutes).
    If resolved_at is within 5 working days:
    Reopen existing ticket (status = 'IN_PROGRESS'), resume SLA, log TICKET_REOPENED.
    If past 5 working days:
    Do NOT reopen. Automatically create new ticket linked via parent_ticket_id,
    copy subject/customer context, log FOLLOWUP_TICKET_CREATED on both tickets.
    """
    now = now_utc or datetime.now(timezone.utc)
    base_resol = ticket.resolved_at or ticket.closed_at or ticket.updated_at
    
    elapsed_working_mins = working_minutes_between(to_ist(base_resol), to_ist(now), holidays)
    FIVE_WORKING_DAYS_MINUTES = 2700

    if elapsed_working_mins <= FIVE_WORKING_DAYS_MINUTES:
        # Within window: Reopen existing
        ticket.status = TicketStatus.IN_PROGRESS
        ticket.resolved_at = None
        ticket.closed_at = None
        ticket.updated_at = now
        
        # Resume SLA if was paused
        resume_sla_if_paused(ticket, holidays, now)
        
        log_audit_event(
            db,
            ticket_id=ticket.id,
            action=AuditAction.TICKET_REOPENED,
            actor_id=customer.id,
            actor_name=customer.name,
            metadata={"reopened_at": now.isoformat(), "elapsed_working_mins": elapsed_working_mins}
        )
        db.commit()
        db.refresh(ticket)
        return True, ticket
    else:
        # Past window: Create new linked ticket
        # Generate new ticket number
        last_id = db.query(Ticket.id).order_by(Ticket.id.desc()).first()
        next_num = (last_id[0] + 1001) if last_id else 1001
        new_ticket_number = f"FD-{next_num}"

        f_due, r_due = calculate_initial_sla_deadlines(to_ist(now), ticket.priority.value, holidays)

        new_ticket = Ticket(
            ticket_number=new_ticket_number,
            subject=f"[Follow-up] {ticket.subject}",
            description=f"Follow-up to {ticket.ticket_number}.\n\nOriginal Subject: {ticket.subject}\nOriginal Description:\n{ticket.description}",
            customer_id=customer.id,
            assignee_id=None,
            priority=ticket.priority,
            status=TicketStatus.OPEN,
            parent_ticket_id=ticket.id,
            created_at=now,
            updated_at=now,
            first_response_due_at=to_utc(f_due),
            resolution_due_at=to_utc(r_due),
        )
        db.add(new_ticket)
        db.flush()

        log_audit_event(
            db,
            ticket_id=ticket.id,
            action=AuditAction.FOLLOWUP_TICKET_CREATED,
            actor_id=customer.id,
            actor_name=customer.name,
            metadata={"new_ticket_id": new_ticket.id, "new_ticket_number": new_ticket.ticket_number}
        )
        log_audit_event(
            db,
            ticket_id=new_ticket.id,
            action=AuditAction.TICKET_CREATED,
            actor_id=customer.id,
            actor_name=customer.name,
            metadata={"parent_ticket_id": ticket.id, "parent_ticket_number": ticket.ticket_number}
        )
        db.commit()
        db.refresh(new_ticket)
        return False, new_ticket

def run_auto_close_inactivity_check(db: Session, holidays: Set[date], as_of: Optional[datetime] = None) -> list[int]:
    """
    If a ticket stays in WAITING_ON_CUSTOMER for >= 5 working days (2,700 working minutes)
    without customer reply, transition to CLOSED and log TICKET_AUTO_CLOSED.
    """
    now = as_of or datetime.now(timezone.utc)
    now_ist = to_ist(now)
    
    waiting_tickets = db.query(Ticket).filter(
        Ticket.status == TicketStatus.WAITING_ON_CUSTOMER,
        Ticket.sla_paused_at.isnot(None)
    ).all()

    closed_ticket_ids = []
    FIVE_WORKING_DAYS_MINUTES = 2700

    for t in waiting_tickets:
        paused_ist = to_ist(t.sla_paused_at)
        working_mins = working_minutes_between(paused_ist, now_ist, holidays)
        if working_mins >= FIVE_WORKING_DAYS_MINUTES:
            t.status = TicketStatus.CLOSED
            t.closed_at = now
            t.updated_at = now
            # Log audit
            log_audit_event(
                db,
                ticket_id=t.id,
                action=AuditAction.TICKET_AUTO_CLOSED,
                actor_id=None,
                actor_name="System Automation",
                metadata={"waiting_working_minutes": working_mins, "threshold": FIVE_WORKING_DAYS_MINUTES}
            )
            closed_ticket_ids.append(t.id)

    if closed_ticket_ids:
        db.commit()

    return closed_ticket_ids
