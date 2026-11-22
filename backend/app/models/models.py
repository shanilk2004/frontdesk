import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum, JSON, Date
)
from sqlalchemy.orm import relationship
from app.database import Base

class UserRole(str, enum.Enum):
    AGENT = "AGENT"
    LEAD = "LEAD"
    CUSTOMER = "CUSTOMER"

class TicketPriority(str, enum.Enum):
    URGENT = "URGENT"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class TicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_ON_CUSTOMER = "WAITING_ON_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class AuditAction(str, enum.Enum):
    TICKET_CREATED = "TICKET_CREATED"
    TICKET_CLAIMED = "TICKET_CLAIMED"
    TICKET_REASSIGNED = "TICKET_REASSIGNED"
    PUBLIC_REPLY_SENT = "PUBLIC_REPLY_SENT"
    CUSTOMER_REPLIED = "CUSTOMER_REPLIED"
    INTERNAL_NOTE_ADDED = "INTERNAL_NOTE_ADDED"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    SLA_PAUSED = "SLA_PAUSED"
    SLA_RESUMED = "SLA_RESUMED"
    TICKET_RESOLVED = "TICKET_RESOLVED"
    TICKET_REOPENED = "TICKET_REOPENED"
    TICKET_AUTO_CLOSED = "TICKET_AUTO_CLOSED"
    FOLLOWUP_TICKET_CREATED = "FOLLOWUP_TICKET_CREATED"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.AGENT)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    tickets_created = relationship("Ticket", back_populates="customer", foreign_keys="Ticket.customer_id")
    assigned_tickets = relationship("Ticket", back_populates="assignee", foreign_keys="Ticket.assignee_id")
    public_messages = relationship("PublicMessage", back_populates="author")
    internal_notes = relationship("InternalNote", back_populates="author")

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String(20), unique=True, index=True, nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    priority = Column(SQLEnum(TicketPriority), nullable=False, default=TicketPriority.MEDIUM)
    status = Column(SQLEnum(TicketStatus), nullable=False, default=TicketStatus.OPEN)

    parent_ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    first_responded_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    first_response_due_at = Column(DateTime, nullable=True)
    resolution_due_at = Column(DateTime, nullable=True)

    sla_paused_at = Column(DateTime, nullable=True)
    total_paused_working_minutes = Column(Integer, default=0, nullable=False)

    customer = relationship("User", foreign_keys=[customer_id], back_populates="tickets_created")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_tickets")
    parent_ticket = relationship("Ticket", remote_side=[id], backref="child_tickets")
    public_messages = relationship("PublicMessage", back_populates="ticket", cascade="all, delete-orphan", order_by="PublicMessage.created_at")
    internal_notes = relationship("InternalNote", back_populates="ticket", cascade="all, delete-orphan", order_by="InternalNote.created_at")
    audit_logs = relationship("AuditLog", back_populates="ticket", cascade="all, delete-orphan", order_by="AuditLog.created_at")

class PublicMessage(Base):
    __tablename__ = "public_messages"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author_role = Column(SQLEnum(UserRole), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    ticket = relationship("Ticket", back_populates="public_messages")
    author = relationship("User", back_populates="public_messages")

class InternalNote(Base):
    __tablename__ = "internal_notes"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    ticket = relationship("Ticket", back_populates="internal_notes")
    author = relationship("User", back_populates="internal_notes")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_name = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    meta = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    ticket = relationship("Ticket", back_populates="audit_logs")

class Holiday(Base):
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
