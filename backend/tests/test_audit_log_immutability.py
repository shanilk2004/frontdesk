"""
INC-0318 — Immutable Audit Log Test
Every state change and communication must be recorded in an append-only audit_logs table.
Enforce immutability at the database level with a trigger that blocks UPDATE and DELETE.
Attempt raw SQL UPDATE and DELETE on audit_logs and assert database raises an exception.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError, OperationalError, InternalError

from app.models.models import AuditLog

def test_audit_log_append_only(db: Session):
    # Verify that inserting works
    log_entry = AuditLog(
        ticket_id=1,
        actor_id=1,
        actor_name="Meera Rao",
        action="TEST_ACTION",
        meta={"key": "initial_value"}
    )
    db.add(log_entry)
    db.commit()
    target_id = log_entry.id
    assert target_id is not None

    # 1. Attempt raw SQL UPDATE -> Must fail with trigger exception
    with pytest.raises((DBAPIError, OperationalError, InternalError)) as exc_update:
        db.execute(text("UPDATE audit_logs SET actor_name = 'Hacker' WHERE id = :id"), {"id": target_id})
        db.commit()

    db.rollback()
    assert "append-only" in str(exc_update.value).lower() or "forbidden" in str(exc_update.value).lower()

    # 2. Attempt raw SQL DELETE -> Must fail with trigger exception
    with pytest.raises((DBAPIError, OperationalError, InternalError)) as exc_delete:
        db.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": target_id})
        db.commit()

    db.rollback()
    assert "append-only" in str(exc_delete.value).lower() or "forbidden" in str(exc_delete.value).lower()
