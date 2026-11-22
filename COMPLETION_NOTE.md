# COMPLETION NOTE: Frontdesk (Arvo Systems Support Platform)

**Candidate Submission Note**

### 1. Deliverables Summary
- **Backend (`backend/`):**
  - FastAPI application with SQLAlchemy 2.0 models: `users`, `tickets`, `public_messages`, `internal_notes`, `audit_logs`, `holidays`.
  - Atomic conditional ticket claiming (`atomic_claim_ticket`) in `app/services/ticket_service.py` preventing double-claiming (INC-0291).
  - Strict separation of customer vs agent schemas and routes preventing internal note leaks (INC-0304).
  - Database trigger enforcing append-only immutability for `audit_logs` (INC-0318).
  - Working-hours SLA engine (`app/services/sla.py`) supporting IST (`Asia/Kolkata`) 09:30–18:30 calendar, holidays, SLA pauses, escalations, auto-close, and 1-week reopen windows.
  - Realistic seed data initializing 9 Arvo agents (including Meera as Lead), 5 customers, festival holidays, and 8 state-representative tickets.
- **Frontend (`frontend/`):**
  - Next.js (App Router, TypeScript) and Tailwind CSS dashboard.
  - Top bar with one-click **Active Agent Switcher** (to test concurrency between agents) and **Mode Toggle** (Agent Workspace vs Customer Portal).
  - KPI strip, dynamic SLA badges (`BREACHED`, `PAUSED`, `URGENT`), and interactive ticket drawer.
  - Dual-tab composer with clear visual segregation for public replies vs amber-highlighted team-only notes.
  - Built-in CSV/JSON export and reopen flow in the Customer Portal.
- **Tests (`backend/tests/`):**
  - 12 comprehensive unit and integration tests passing with 100% success rate:
    - `test_sla_working_hours.py`: IST calendar calculations, Friday evening to Sunday morning carryover, urgent same-day resolution, pause & resume, escalation.
    - `test_concurrency_claim.py`: Atomic conditional update test verifying that concurrent claims result in 1 success and 1 HTTP 409 Conflict.
    - `test_internal_notes_isolation.py`: Verified internal notes are never surfaced in customer endpoints or exports.
    - `test_audit_log_immutability.py`: Verified DB trigger blocks raw SQL updates and deletes.
    - `test_lifecycle_rules.py`: Auto-close on 5 days inactivity, reopen within 1 week, and new-ticket creation past 1 week.

### 2. Testing Instructions for Evaluators
1. **Double-Claim Concurrency (INC-0291):**
   - In the Agent Workspace, select the unassigned urgent ticket `FD-1002`.
   - Open another browser tab or switch the Active Agent to another agent (e.g., from Meera to Aarav).
   - Claim the ticket in Tab 1 (succeeds).
   - Attempting to claim in Tab 2 or as another agent immediately returns HTTP 409 with an error toast indicating the ticket is already held.
2. **Zero-Leak Internal Notes (INC-0304):**
   - In Agent Workspace, open `FD-1001` or `FD-1003` and view the amber-tinted internal notes with lock icons.
   - Switch mode to "Customer Portal (Zero-Leak)" and select the customer.
   - Observe that only public replies are visible. Download the JSON/CSV export to verify that internal notes are absent.
3. **Working-Hours SLA & Pause/Resume:**
   - Send a reply in Agent Workspace with the "Mark as Waiting on Customer & pause SLA" checkbox checked. Notice status changes to `WAITING_ON_CUSTOMER` and the SLA badge turns to `PAUSED`.
   - Switch to Customer Portal and reply to the ticket. Notice the SLA timer automatically resumes and the status changes to `IN_PROGRESS`.
