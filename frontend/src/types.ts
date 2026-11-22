export interface User {
  id: number;
  name: string;
  email: string;
  role: 'AGENT' | 'LEAD' | 'CUSTOMER';
  created_at: string;
}

export interface PublicMessage {
  id: number;
  ticket_id: number;
  author_id: number;
  author_role: 'AGENT' | 'CUSTOMER';
  author_name?: string;
  body: string;
  created_at: string;
}

export interface InternalNote {
  id: number;
  ticket_id: number;
  author_id: number;
  author_name?: string;
  body: string;
  created_at: string;
}

export interface AuditLog {
  id: number;
  ticket_id: number;
  actor_id?: number;
  actor_name: string;
  action: string;
  metadata?: any;
  created_at: string;
}

export interface TicketSLAStatus {
  is_breached: boolean;
  breach_type?: 'FIRST_RESPONSE_BREACHED' | 'RESOLUTION_BREACHED' | 'BOTH' | null;
  is_paused: boolean;
  remaining_response_minutes?: number | null;
  remaining_resolution_minutes?: number | null;
  first_response_due_at?: string | null;
  resolution_due_at?: string | null;
  total_paused_working_minutes: number;
}

export interface Ticket {
  id: number;
  ticket_number: string;
  subject: string;
  description: string;
  status: 'OPEN' | 'IN_PROGRESS' | 'WAITING_ON_CUSTOMER' | 'RESOLVED' | 'CLOSED';
  priority: 'URGENT' | 'MEDIUM' | 'LOW';
  customer_id?: number;
  customer_name?: string;
  customer_email?: string;
  assignee_id?: number | null;
  assignee_name?: string | null;
  created_at: string;
  updated_at: string;
  first_responded_at?: string | null;
  resolved_at?: string | null;
  closed_at?: string | null;
  first_response_due_at?: string | null;
  resolution_due_at?: string | null;
  sla_paused_at?: string | null;
  total_paused_working_minutes: number;
  parent_ticket_id?: number | null;
  sla?: TicketSLAStatus;
  public_messages?: PublicMessage[];
  internal_notes?: InternalNote[];
  audit_logs?: AuditLog[];
}

export interface Holiday {
  id: number;
  date: string;
  name: string;
}
