from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict
from app.models.models import UserRole, TicketPriority, TicketStatus

# User schemas
class UserBase(BaseModel):
    name: str
    email: str
    role: UserRole

class UserOut(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Public Message schemas
class PublicMessageBase(BaseModel):
    body: str

class PublicMessageCreate(PublicMessageBase):
    pass

class PublicMessageOut(PublicMessageBase):
    id: int
    ticket_id: int
    author_id: int
    author_role: UserRole
    author_name: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Internal Note schemas (AGENT-ONLY)
class InternalNoteBase(BaseModel):
    body: str

class InternalNoteCreate(InternalNoteBase):
    pass

class InternalNoteOut(InternalNoteBase):
    id: int
    ticket_id: int
    author_id: int
    author_name: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Audit Log schemas
class AuditLogOut(BaseModel):
    id: int
    ticket_id: int
    actor_id: Optional[int]
    actor_name: str
    action: str
    metadata: Optional[Any] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# Holiday schemas
class HolidayBase(BaseModel):
    date: date
    name: str

class HolidayCreate(HolidayBase):
    pass

class HolidayOut(HolidayBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# SLA State Computed Details
class TicketSLAStatus(BaseModel):
    is_breached: bool
    breach_type: Optional[str] = None # FIRST_RESPONSE_BREACHED, RESOLUTION_BREACHED, BOTH, or None
    is_paused: bool
    remaining_response_minutes: Optional[int] = None
    remaining_resolution_minutes: Optional[int] = None
    first_response_due_at: Optional[datetime] = None
    resolution_due_at: Optional[datetime] = None
    total_paused_working_minutes: int

# Ticket Base & Create
class TicketCreate(BaseModel):
    subject: str
    description: str
    customer_id: int
    priority: TicketPriority = TicketPriority.MEDIUM

class CustomerTicketCreate(BaseModel):
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM

# STRICT SEPARATION: AgentTicketDetail vs CustomerTicketDetail (INC-0304)
class CustomerTicketItem(BaseModel):
    id: int
    ticket_number: str
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime
    updated_at: datetime
    first_responded_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    parent_ticket_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

class CustomerTicketDetail(CustomerTicketItem):
    public_messages: List[PublicMessageOut] = []
    # Explicitly ZERO internal_notes and ZERO audit_logs

class AgentTicketItem(BaseModel):
    id: int
    ticket_number: str
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    customer_id: int
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    assignee_id: Optional[int] = None
    assignee_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    first_responded_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    first_response_due_at: Optional[datetime] = None
    resolution_due_at: Optional[datetime] = None
    sla_paused_at: Optional[datetime] = None
    total_paused_working_minutes: int = 0
    parent_ticket_id: Optional[int] = None
    sla: Optional[TicketSLAStatus] = None
    model_config = ConfigDict(from_attributes=True)

class AgentTicketDetail(AgentTicketItem):
    public_messages: List[PublicMessageOut] = []
    internal_notes: List[InternalNoteOut] = []
    audit_logs: List[AuditLogOut] = []

# Action Requests
class TicketReplyRequest(BaseModel):
    body: str
    wait_for_customer: bool = False

class TicketUpdateRequest(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None

class TicketReopenResponse(BaseModel):
    reopened: bool
    ticket_id: int
    ticket_number: str
    message: str
