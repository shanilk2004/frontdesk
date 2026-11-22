import random
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.models.models import (
    User, UserRole, Ticket, TicketPriority, TicketStatus,
    PublicMessage, InternalNote, AuditLog, Holiday, AuditAction
)
from app.services.sla import IST, calculate_initial_sla_deadlines, to_utc

def seed_database(db: Session):
    # Check if data already exists
    if db.query(User).first():
        return

    # 1. Seed 9 Support Agents (including Meera as Lead)
    agents_data = [
        ("Meera Rao", "meera@arvo.internal", UserRole.LEAD),
        ("Aarav Patel", "aarav@arvo.internal", UserRole.AGENT),
        ("Pooja Nair", "pooja@arvo.internal", UserRole.AGENT),
        ("Rohan Sharma", "rohan@arvo.internal", UserRole.AGENT),
        ("Siddharth Verma", "siddharth@arvo.internal", UserRole.AGENT),
        ("Ananya Iyer", "ananya@arvo.internal", UserRole.AGENT),
        ("Kavita Menon", "kavita@arvo.internal", UserRole.AGENT),
        ("Vikram Singh", "vikram@arvo.internal", UserRole.AGENT),
        ("Divya Joshi", "divya@arvo.internal", UserRole.AGENT),
    ]

    agents = []
    for name, email, role in agents_data:
        agent = User(name=name, email=email, role=role)
        db.add(agent)
        agents.append(agent)

    # 2. Seed 5 Customers
    customers_data = [
        ("Acme Corp (Ramesh Kumar)", "ramesh@acme.com", UserRole.CUSTOMER),
        ("FinTech Nexus (Sunita Rao)", "sunita@fintechnexus.io", UserRole.CUSTOMER),
        ("Zomato Logistics (Karthik B)", "karthik@zomato-logistics.test", UserRole.CUSTOMER),
        ("Skyline Retail (Neha Gupta)", "neha@skylineretail.in", UserRole.CUSTOMER),
        ("Apex Cloud (Aditya Birla)", "aditya@apexcloud.co", UserRole.CUSTOMER),
    ]

    customers = []
    for name, email, role in customers_data:
        cust = User(name=name, email=email, role=role)
        db.add(cust)
        customers.append(cust)

    # 3. Seed Indian Festival Holidays
    # Using 2026 dates (e.g. Republic Day, Independence Day, Diwali)
    holidays_data = [
        (date(2026, 1, 26), "Republic Day"),
        (date(2026, 8, 15), "Independence Day"),
        (date(2026, 11, 8), "Diwali"),
    ]
    holidays = []
    holiday_dates = set()
    for h_date, h_name in holidays_data:
        h = Holiday(date=h_date, name=h_name)
        db.add(h)
        holidays.append(h)
        holiday_dates.add(h_date)

    db.commit()

    # Refresh IDs
    for a in agents: db.refresh(a)
    for c in customers: db.refresh(c)

    now = datetime.now(timezone.utc)
    meera = agents[0]
    aarav = agents[1]
    pooja = agents[2]

    # Helper to calculate SLA deadlines
    def get_deadlines(dt_utc: datetime, prio: str):
        dt_ist = dt_utc.astimezone(IST)
        f_ist, r_ist = calculate_initial_sla_deadlines(dt_ist, prio, holiday_dates)
        return to_utc(f_ist), to_utc(r_ist)

    # 4. Seed ~10 Realistic Tickets covering every scenario
    
    # Ticket 1: Already Breached URGENT Ticket (created 5 days ago, unresolved, no first response)
    t1_created = now - timedelta(days=5)
    t1_f_due, t1_r_due = get_deadlines(t1_created, "URGENT")
    t1 = Ticket(
        ticket_number="FD-1001",
        subject="CRITICAL: Payment Gateway Webhook dropping 500 errors",
        description="Our checkout pipeline is throwing HTTP 500 when calling the Arvo payment settlement endpoint. Production is halted.",
        customer_id=customers[0].id,
        assignee_id=aarav.id,
        priority=TicketPriority.URGENT,
        status=TicketStatus.IN_PROGRESS,
        created_at=t1_created,
        updated_at=t1_created,
        first_response_due_at=t1_f_due,
        resolution_due_at=t1_r_due,
    )
    db.add(t1)
    db.flush()
    db.add(AuditLog(ticket_id=t1.id, actor_id=customers[0].id, actor_name=customers[0].name, action=AuditAction.TICKET_CREATED, meta={"priority": "URGENT"}, created_at=t1_created))
    db.add(AuditLog(ticket_id=t1.id, actor_id=aarav.id, actor_name=aarav.name, action=AuditAction.TICKET_CLAIMED, meta={}, created_at=t1_created + timedelta(minutes=15)))
    db.add(InternalNote(ticket_id=t1.id, author_id=aarav.id, body="Investigating server logs in cluster-us-east. Webhook timeout seems related to Redis queue pressure.", created_at=t1_created + timedelta(minutes=20)))

    # Ticket 2: Unassigned URGENT Ticket (Perfect for testing INC-0291 Atomic Double-Claim!)
    t2_created = now - timedelta(minutes=30)
    t2_f_due, t2_r_due = get_deadlines(t2_created, "URGENT")
    t2 = Ticket(
        ticket_number="FD-1002",
        subject="URGENT: Entire analytics dashboard returning blank white screen",
        description="None of our execs can access the quarterly reporting dashboard. We have an investor call in 2 hours.",
        customer_id=customers[1].id,
        assignee_id=None, # UNASSIGNED
        priority=TicketPriority.URGENT,
        status=TicketStatus.OPEN,
        created_at=t2_created,
        updated_at=t2_created,
        first_response_due_at=t2_f_due,
        resolution_due_at=t2_r_due,
    )
    db.add(t2)
    db.flush()
    db.add(AuditLog(ticket_id=t2.id, actor_id=customers[1].id, actor_name=customers[1].name, action=AuditAction.TICKET_CREATED, meta={"priority": "URGENT"}, created_at=t2_created))

    # Ticket 3: Waiting on Customer with Paused SLA
    t3_created = now - timedelta(hours=14)
    t3_f_due, t3_r_due = get_deadlines(t3_created, "MEDIUM")
    t3_resp_at = now - timedelta(hours=8)
    t3 = Ticket(
        ticket_number="FD-1003",
        subject="Missing invoice PDF export for October statement",
        description="When clicking Download PDF on invoice #9401, a corrupt 0KB file is received.",
        customer_id=customers[2].id,
        assignee_id=pooja.id,
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.WAITING_ON_CUSTOMER,
        created_at=t3_created,
        updated_at=t3_resp_at,
        first_responded_at=t3_resp_at,
        first_response_due_at=t3_f_due,
        resolution_due_at=t3_r_due,
        sla_paused_at=t3_resp_at,
        total_paused_working_minutes=0
    )
    db.add(t3)
    db.flush()
    db.add(PublicMessage(ticket_id=t3.id, author_id=customers[2].id, author_role=UserRole.CUSTOMER, body="When clicking Download PDF on invoice #9401, a corrupt 0KB file is received.", created_at=t3_created))
    db.add(PublicMessage(ticket_id=t3.id, author_id=pooja.id, author_role=UserRole.AGENT, body="Hi Karthik, could you please confirm if this happens on Chrome or Firefox as well? We cleared the server render cache.", created_at=t3_resp_at))
    db.add(InternalNote(ticket_id=t3.id, author_id=pooja.id, body="Internal Note: Chromium headless renderer crashed during memory spike. Might need pool restart.", created_at=t3_resp_at + timedelta(minutes=2)))
    db.add(AuditLog(ticket_id=t3.id, actor_id=pooja.id, actor_name=pooja.name, action=AuditAction.SLA_PAUSED, meta={"status": "WAITING_ON_CUSTOMER"}, created_at=t3_resp_at))

    # Ticket 4: Another Waiting on Customer (Waiting for 6 days -> Candidate for Auto-Close test!)
    t4_created = now - timedelta(days=9)
    t4_paused = now - timedelta(days=8) # >= 5 working days ago
    t4_f_due, t4_r_due = get_deadlines(t4_created, "LOW")
    t4 = Ticket(
        ticket_number="FD-1004",
        subject="How do I change the default brand color in tenant settings?",
        description="We want to change our portal theme to #0052CC.",
        customer_id=customers[3].id,
        assignee_id=meera.id,
        priority=TicketPriority.LOW,
        status=TicketStatus.WAITING_ON_CUSTOMER,
        created_at=t4_created,
        updated_at=t4_paused,
        first_responded_at=t4_paused,
        first_response_due_at=t4_f_due,
        resolution_due_at=t4_r_due,
        sla_paused_at=t4_paused,
        total_paused_working_minutes=0
    )
    db.add(t4)
    db.flush()
    db.add(PublicMessage(ticket_id=t4.id, author_id=meera.id, author_role=UserRole.AGENT, body="You can navigate to Settings > Theme. Let us know if you need more help!", created_at=t4_paused))
    db.add(AuditLog(ticket_id=t4.id, actor_id=meera.id, actor_name=meera.name, action=AuditAction.SLA_PAUSED, meta={"status": "WAITING_ON_CUSTOMER"}, created_at=t4_paused))

    # Ticket 5: Resolved 2 Days Ago (Within 1-week window -> Reopenable!)
    t5_created = now - timedelta(days=3)
    t5_f_due, t5_r_due = get_deadlines(t5_created, "MEDIUM")
    t5_resol = now - timedelta(days=2)
    t5 = Ticket(
        ticket_number="FD-1005",
        subject="Webhook signing key regeneration failed",
        description="The regeneration button was spinning indefinitely.",
        customer_id=customers[4].id,
        assignee_id=aarav.id,
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.RESOLVED,
        created_at=t5_created,
        updated_at=t5_resol,
        first_responded_at=t5_created + timedelta(minutes=45),
        resolved_at=t5_resol,
        first_response_due_at=t5_f_due,
        resolution_due_at=t5_r_due,
    )
    db.add(t5)
    db.flush()
    db.add(PublicMessage(ticket_id=t5.id, author_id=aarav.id, author_role=UserRole.AGENT, body="We flushed the cache and the key regeneration works cleanly now.", created_at=t5_resol))
    db.add(AuditLog(ticket_id=t5.id, actor_id=aarav.id, actor_name=aarav.name, action=AuditAction.TICKET_RESOLVED, meta={}, created_at=t5_resol))

    # Ticket 6: Resolved 14 Days Ago (Past 1-week window -> Reopen will create new linked ticket!)
    t6_created = now - timedelta(days=20)
    t6_resol = now - timedelta(days=14)
    t6_f_due, t6_r_due = get_deadlines(t6_created, "LOW")
    t6 = Ticket(
        ticket_number="FD-1006",
        subject="Request for custom audit export format",
        description="Can we get the weekly user activity in NDJSON format?",
        customer_id=customers[0].id,
        assignee_id=pooja.id,
        priority=TicketPriority.LOW,
        status=TicketStatus.RESOLVED,
        created_at=t6_created,
        updated_at=t6_resol,
        first_responded_at=t6_created + timedelta(hours=2),
        resolved_at=t6_resol,
        first_response_due_at=t6_f_due,
        resolution_due_at=t6_r_due,
    )
    db.add(t6)
    db.flush()
    db.add(AuditLog(ticket_id=t6.id, actor_id=pooja.id, actor_name=pooja.name, action=AuditAction.TICKET_RESOLVED, meta={}, created_at=t6_resol))

    # Ticket 7: Open Fresh Ticket (Medium priority)
    t7_created = now - timedelta(minutes=10)
    t7_f_due, t7_r_due = get_deadlines(t7_created, "MEDIUM")
    t7 = Ticket(
        ticket_number="FD-1007",
        subject="Rate limit headers (X-RateLimit-Remaining) not showing in API response",
        description="We are building an SDK client and need rate limit visibility.",
        customer_id=customers[1].id,
        assignee_id=None,
        priority=TicketPriority.MEDIUM,
        status=TicketStatus.OPEN,
        created_at=t7_created,
        updated_at=t7_created,
        first_response_due_at=t7_f_due,
        resolution_due_at=t7_r_due,
    )
    db.add(t7)

    # Ticket 8: In Progress with Meera (Lead)
    t8_created = now - timedelta(hours=2)
    t8_f_due, t8_r_due = get_deadlines(t8_created, "LOW")
    t8 = Ticket(
        ticket_number="FD-1008",
        subject="SSO SAML Certificate expiration notice",
        description="Our Okta IdP certificate will rotate next Tuesday. Please update metadata.",
        customer_id=customers[2].id,
        assignee_id=meera.id,
        priority=TicketPriority.LOW,
        status=TicketStatus.IN_PROGRESS,
        created_at=t8_created,
        updated_at=t8_created,
        first_responded_at=t8_created + timedelta(minutes=15),
        first_response_due_at=t8_f_due,
        resolution_due_at=t8_r_due,
    )
    db.add(t8)

    db.commit()
