-- Frontdesk PostgreSQL Initialization & Immutable Audit Log Trigger (INC-0318)

-- Function to prevent mutation (UPDATE/DELETE) on audit_logs
CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs is append-only: % is forbidden', TG_OP;
END;
$$ LANGUAGE plpgsql;

-- Trigger definition for PostgreSQL
DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs;
CREATE TRIGGER trg_audit_logs_immutable
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
