# Frontdesk — Arvo Systems Support Platform

Frontdesk is a customer support ticketing web application designed specifically for **Arvo Systems** (9 support agents, ~40 tickets/day) to replace their previous spreadsheet and WhatsApp workflow.

---

## 1. System Architecture & Tech Stack

- **Backend:** Python 3.11+ with **FastAPI**, SQLAlchemy 2.0, Pydantic v2, `pytest`.
- **Database:** PostgreSQL (with Neon/Supabase compatibility; also runs with SQLite for lightweight local offline testing).
- **Frontend:** Next.js (App Router, TypeScript) + Tailwind CSS + Lucide Icons.
- **SLA Engine:** Dedicated IST (`Asia/Kolkata`) business calendar working-hours calculator (Mon-Fri 09:30–18:30 IST, skipping weekends and configurable festival holidays).

---

## 2. Non-Negotiable Engineering Invariants (From Incident Reports)

### A. INC-0291 — Atomic Ticket Claiming (Zero Double-Claiming)
Two agents can **never** claim the same unassigned ticket simultaneously:
- Enforced at the database level using an atomic conditional update:
  ```sql
  UPDATE tickets
  SET assignee_id = :agent_id, status = 'IN_PROGRESS', updated_at = NOW()
  WHERE id = :ticket_id AND assignee_id IS NULL;
  ```
- If 0 rows are updated, the backend immediately raises **HTTP 409 Conflict** with an informative message identifying the agent who already holds the ticket.
- Avoids check-then-act memory race conditions. Evaluators can test this in two browser tabs or by using the built-in active agent switcher.

### B. INC-0304 — Zero-Leak Internal Team Notes
Private internal team notes are strictly segregated from customers:
- Public customer messages are stored in `public_messages`; private internal notes are stored in a dedicated `internal_notes` table.
- Customer-facing routes (`/api/customer/...`) and export endpoints (`/api/customer/tickets/{id}/export?format=json|csv`) **never query or join `internal_notes`**.
- Strictly separated Pydantic response models (`AgentTicketDetail` vs `CustomerTicketDetail`) ensure that internal note fields and audit logs are physically absent from customer responses.
- In the UI, internal notes feature a distinct amber card with a lock icon and a banner: `TEAM ONLY — NEVER SHOWN TO CUSTOMER`.

### C. INC-0318 — Immutable Audit Log
Every state change, assignment, reply, priority update, and pause/resume is recorded in `audit_logs`.
- PostgreSQL trigger blocks `UPDATE` and `DELETE` on `audit_logs`:
  ```sql
  CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
  RETURNS TRIGGER AS $$
  BEGIN
      RAISE EXCEPTION 'audit_logs is append-only: % is forbidden', TG_OP;
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER trg_audit_logs_immutable
  BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
  ```
- Also mirrored in SQLite with `BEFORE UPDATE` and `BEFORE DELETE` triggers that execute `SELECT RAISE(ABORT, 'audit_logs is append-only')`.

---

## 3. Working-Hours SLA Engine (`app/services/sla.py`)

- **Calendar:** Monday to Friday, 09:30 to 18:30 IST (9 working hours = 540 working minutes/day).
- **Holidays:** Weekends (Sat/Sun) and dates stored in the `holidays` table are excluded.
- **Priority SLA Targets:**
  - **URGENT:** First response within 2 working hours (120 mins). Resolution by same working day (18:30 IST, ensuring at least 2 working hours).
  - **MEDIUM:** First response within 4.5 working hours (270 mins). Resolution within 3 working days (1,620 working mins).
  - **LOW:** First response within 1 working day (540 mins). Resolution within 5 working days (2,700 working mins).
- **SLA Pause on "Waiting on Customer":**
  - When an agent sets status to `WAITING_ON_CUSTOMER`, `sla_paused_at` is stamped.
  - When customer replies (or agent resumes), the paused working minutes are calculated and added to `total_paused_working_minutes`, extending due dates accordingly.
- **Auto-Close Inactivity Rule:**
  - If a ticket remains in `WAITING_ON_CUSTOMER` for $\ge$ 5 working days (2,700 working minutes) without reply, it auto-transitions to `CLOSED` with a `TICKET_AUTO_CLOSED` audit log.
  - Callable via `POST /api/admin/run-auto-close`.
- **Reopen Window (1 Working Week):**
  - If customer reopens within 5 working days of resolution, ticket is reopened (`IN_PROGRESS`).
  - If past 5 working days, an automatic follow-up ticket is created and linked via `parent_ticket_id`.
- **Priority Escalation:**
  - Changing priority mid-ticket recalculates deadlines from `created_at` using the new priority's budget plus accumulated pause minutes. If the new deadline has already passed, the ticket immediately surfaces as breached.

---

## 4. How to Run Locally

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- (Optional) Docker & Docker Compose for PostgreSQL

### Step 1: Start PostgreSQL (Optional)
```bash
docker compose up -d
```
*(If Docker is not installed, Frontdesk defaults seamlessly to `sqlite:///./frontdesk.db` with identical triggers and concurrency safeguards).*

### Step 2: Start Backend
The backend is already pre-configured to connect to your live Neon PostgreSQL instance via `backend/.env`.
```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
- API Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### Step 3: Start Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## 5. Running Automated Tests

To run the complete automated test suite verifying all engineering invariants:
```bash
$env:PYTHONPATH="backend"
python -m pytest backend/tests/test_sla_working_hours.py backend/tests/test_audit_log_immutability.py backend/tests/test_internal_notes_isolation.py backend/tests/test_concurrency_claim.py backend/tests/test_lifecycle_rules.py -v
```
All 12 tests verify SLA calculations, zero double-claiming, zero-leak notes isolation, DB immutability triggers, and reopen/auto-close rules.
