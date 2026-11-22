"""
Main FastAPI Application for Frontdesk (Arvo Systems Support Platform)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.models.models import AuditLog
from app.routers import agent, customer, admin
from app.seed import seed_database

def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as conn:
            if conn.dialect.name == "sqlite":
                conn.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_update
                    BEFORE UPDATE ON audit_logs
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_logs is append-only: UPDATE is forbidden');
                    END;
                """))
                conn.execute(text("""
                    CREATE TRIGGER IF NOT EXISTS trg_audit_logs_no_delete
                    BEFORE DELETE ON audit_logs
                    BEGIN
                        SELECT RAISE(ABORT, 'audit_logs is append-only: DELETE is forbidden');
                    END;
                """))
            elif conn.dialect.name == "postgresql":
                conn.execute(text("""
                    CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        RAISE EXCEPTION 'audit_logs is append-only: % is forbidden', TG_OP;
                    END;
                    $$ LANGUAGE plpgsql;
                """))
                conn.execute(text("""
                    DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;
                    CREATE TRIGGER trg_audit_logs_immutable
                    BEFORE UPDATE OR DELETE ON audit_logs
                    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
                """))
    except Exception as e:
        print(f"Trigger setup notice: {e}")

    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

# Initialize DB synchronously upon module load if in main process
init_db()

app = FastAPI(
    title="Frontdesk API — Arvo Systems Support Platform",
    description="High-reliability customer support ticketing platform with atomic claiming, working-hours SLA engine, and zero-leak notes isolation.",
    version="1.0.0",
)

# CORS configuration via ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoint
@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "app": "Frontdesk",
        "environment": settings.ENVIRONMENT,
        "database": settings.DATABASE_URL.split("://")[0]
    }

# Register Routers
app.include_router(agent.router)
app.include_router(customer.router)
app.include_router(admin.router)
