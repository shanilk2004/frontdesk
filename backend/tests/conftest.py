"""
Pytest fixtures and database test harness for Frontdesk tests.
Uses a separate isolated test database.
"""

import os
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models.models import AuditLog, User, UserRole, Holiday
from app.main import app
from app.seed import seed_database

TEST_DB_URL = "sqlite:///./test_frontdesk.db"

test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False, "timeout": 15}, future=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def create_sqlite_audit_triggers(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER IF EXISTS trg_audit_logs_no_update;"))
        conn.execute(text("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete;"))
        conn.execute(text("""
            CREATE TRIGGER trg_audit_logs_no_update
            BEFORE UPDATE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'audit_logs is append-only: UPDATE is forbidden');
            END;
        """))
        conn.execute(text("""
            CREATE TRIGGER trg_audit_logs_no_delete
            BEFORE DELETE ON audit_logs
            BEGIN
                SELECT RAISE(ABORT, 'audit_logs is append-only: DELETE is forbidden');
            END;
        """))

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    create_sqlite_audit_triggers(test_engine)
    db = TestingSessionLocal()
    seed_database(db)
    db.close()
    yield
    # Cleanup after session
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test_frontdesk.db"):
        try:
            os.remove("./test_frontdesk.db")
        except Exception:
            pass

@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client():
    # Use normal app client against test db
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
