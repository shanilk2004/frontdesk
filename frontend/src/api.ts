const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function fetchWithActor(url: string, actorId: number, options: RequestInit = {}) {
  const headers = {
    'Content-Type': 'application/json',
    'X-Actor-Id': String(actorId),
    ...(options.headers || {}),
  };
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });
  return res;
}

export const api = {
  // Agent
  getAgents: () => fetch(`${API_BASE}/api/agent/agents`).then(r => r.json()),
  getAgentTickets: (actorId: number, params: Record<string, any> = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') q.append(k, String(v));
    });
    return fetchWithActor(`/api/agent/tickets?${q.toString()}`, actorId).then(r => r.json());
  },
  getAgentTicketDetail: (actorId: number, id: number) =>
    fetchWithActor(`/api/agent/tickets/${id}`, actorId).then(r => r.json()),
  claimTicket: async (actorId: number, id: number) => {
    const res = await fetchWithActor(`/api/agent/tickets/${id}/claim`, actorId, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to claim ticket');
    }
    return res.json();
  },
  replyTicket: (actorId: number, id: number, body: string, wait_for_customer: boolean) =>
    fetchWithActor(`/api/agent/tickets/${id}/reply`, actorId, {
      method: 'POST',
      body: JSON.stringify({ body, wait_for_customer }),
    }).then(r => r.json()),
  addInternalNote: (actorId: number, id: number, body: string) =>
    fetchWithActor(`/api/agent/tickets/${id}/notes`, actorId, {
      method: 'POST',
      body: JSON.stringify({ body }),
    }).then(r => r.json()),
  updateTicket: (actorId: number, id: number, data: { status?: string; priority?: string }) =>
    fetchWithActor(`/api/agent/tickets/${id}`, actorId, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }).then(r => r.json()),
  getAuditLogs: (actorId: number, id: number) =>
    fetchWithActor(`/api/agent/tickets/${id}/audit`, actorId).then(r => r.json()),
  createAgentTicket: (actorId: number, data: { customer_id: number; subject: string; description: string; priority: string }) =>
    fetchWithActor(`/api/agent/tickets`, actorId, {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(r => r.json()),

  // Customer
  getCustomers: () => fetch(`${API_BASE}/api/customers`).then(r => r.json()),
  getCustomerTickets: (customerId: number) =>
    fetch(`${API_BASE}/api/customer/tickets?customer_id=${customerId}`).then(r => r.json()),
  getCustomerTicketDetail: (customerId: number, id: number) =>
    fetch(`${API_BASE}/api/customer/tickets/${id}?customer_id=${customerId}`).then(r => r.json()),
  createCustomerTicket: (customerId: number, data: { subject: string; description: string; priority: string }) =>
    fetch(`${API_BASE}/api/customer/tickets?customer_id=${customerId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(r => r.json()),
  customerReply: (customerId: number, id: number, body: string) =>
    fetch(`${API_BASE}/api/customer/tickets/${id}/reply?customer_id=${customerId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body }),
    }).then(r => r.json()),
  customerReopen: (customerId: number, id: number) =>
    fetch(`${API_BASE}/api/customer/tickets/${id}/reopen?customer_id=${customerId}`, {
      method: 'POST',
    }).then(r => r.json()),
  exportCustomerUrl: (customerId: number, id: number, format: 'json' | 'csv') =>
    `${API_BASE}/api/customer/tickets/${id}/export?customer_id=${customerId}&format=${format}`,

  // Admin
  getHolidays: () => fetch(`${API_BASE}/api/holidays`).then(r => r.json()),
  addHoliday: (date: string, name: string) =>
    fetch(`${API_BASE}/api/holidays`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, name }),
    }).then(r => r.json()),
  triggerAutoClose: (as_of?: string) =>
    fetch(`${API_BASE}/api/admin/run-auto-close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ as_of: as_of || null }),
    }).then(r => r.json()),
};
