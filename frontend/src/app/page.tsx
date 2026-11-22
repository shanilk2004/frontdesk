'use client';

import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Clock,
  Lock,
  MessageSquare,
  Send,
  UserCheck,
  ShieldAlert,
  Pause,
  Play,
  RotateCcw,
  Download,
  PlusCircle,
  FileText,
  History,
  CheckCircle2,
  Calendar,
  Search,
  RefreshCw,
  ExternalLink,
  Users
} from 'lucide-react';
import { api } from '@/api';
import { User, Ticket, PublicMessage, InternalNote, AuditLog, Holiday } from '@/types';

export default function FrontdeskApp() {
  // Global State
  const [mode, setMode] = useState<'AGENT' | 'CUSTOMER'>('AGENT');
  const [agents, setAgents] = useState<User[]>([]);
  const [customers, setCustomers] = useState<User[]>([]);
  const [activeAgentId, setActiveAgentId] = useState<number>(1); // Default to Meera (Lead)
  const [activeCustomerId, setActiveCustomerId] = useState<number>(10); // Default to first customer

  // Agent Queue State
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<number | null>(null);
  const [ticketDetail, setTicketDetail] = useState<Ticket | null>(null);
  const [filterType, setFilterType] = useState<'ALL' | 'MY' | 'UNASSIGNED' | 'BREACHED' | 'WAITING'>('ALL');
  const [priorityFilter, setPriorityFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Composer State
  const [activeTab, setActiveTab] = useState<'REPLY' | 'NOTE' | 'AUDIT'>('REPLY');
  const [replyText, setReplyText] = useState<string>('');
  const [waitForCustomer, setWaitForCustomer] = useState<boolean>(false);
  const [internalNoteText, setInternalNoteText] = useState<string>('');

  // Modals & Panels
  const [showNewTicketModal, setShowNewTicketModal] = useState<boolean>(false);
  const [newSubject, setNewSubject] = useState<string>('');
  const [newDescription, setNewDescription] = useState<string>('');
  const [newPriority, setNewPriority] = useState<'URGENT' | 'MEDIUM' | 'LOW'>('MEDIUM');
  const [newTicketCustomerId, setNewTicketCustomerId] = useState<number>(10);

  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [showHolidaysModal, setShowHolidaysModal] = useState<boolean>(false);
  const [newHolidayDate, setNewHolidayDate] = useState<string>('');
  const [newHolidayName, setNewHolidayName] = useState<string>('');

  // Trigger toast
  const showToast = (text: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 5000);
  };

  // Initial Load
  useEffect(() => {
    api.getAgents().then(data => {
      setAgents(data);
      if (data.length > 0 && !activeAgentId) setActiveAgentId(data[0].id);
    }).catch(console.error);

    api.getCustomers().then(data => {
      setCustomers(data);
      if (data.length > 0) {
        setActiveCustomerId(data[0].id);
        setNewTicketCustomerId(data[0].id);
      }
    }).catch(console.error);

    api.getHolidays().then(setHolidays).catch(console.error);
  }, []);

  // Fetch Tickets on agent change, mode change, or filters
  const loadTickets = async () => {
    setIsLoading(true);
    try {
      if (mode === 'AGENT') {
        const params: any = {};
        if (filterType === 'MY') params.assignee_id = activeAgentId;
        if (filterType === 'UNASSIGNED') params.unassigned = true;
        if (filterType === 'BREACHED') params.breached_only = true;
        if (filterType === 'WAITING') params.status = 'WAITING_ON_CUSTOMER';
        if (priorityFilter) params.priority = priorityFilter;

        const data = await api.getAgentTickets(activeAgentId, params);
        setTickets(data);
        if (data.length > 0 && !selectedTicketId) {
          setSelectedTicketId(data[0].id);
        }
      } else {
        const data = await api.getCustomerTickets(activeCustomerId);
        setTickets(data);
        if (data.length > 0 && !selectedTicketId) {
          setSelectedTicketId(data[0].id);
        }
      }
    } catch (err: any) {
      console.error(err);
      showToast('Error loading tickets from server', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTickets();
  }, [mode, activeAgentId, activeCustomerId, filterType, priorityFilter]);

  // Load Single Ticket Detail
  const loadTicketDetail = async (id: number) => {
    try {
      if (mode === 'AGENT') {
        const detail = await api.getAgentTicketDetail(activeAgentId, id);
        setTicketDetail(detail);
      } else {
        const detail = await api.getCustomerTicketDetail(activeCustomerId, id);
        setTicketDetail(detail);
      }
    } catch (err: any) {
      console.error(err);
      showToast('Error loading ticket details', 'error');
    }
  };

  useEffect(() => {
    if (selectedTicketId) {
      loadTicketDetail(selectedTicketId);
    } else {
      setTicketDetail(null);
    }
  }, [selectedTicketId, mode, activeAgentId, activeCustomerId]);

  // Actions: Claim
  const handleClaim = async (ticketId: number) => {
    try {
      await api.claimTicket(activeAgentId, ticketId);
      showToast(`Ticket claimed successfully!`, 'success');
      loadTickets();
      loadTicketDetail(ticketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Actions: Agent Public Reply
  const handleAgentReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replyText.trim() || !selectedTicketId) return;

    try {
      await api.replyTicket(activeAgentId, selectedTicketId, replyText, waitForCustomer);
      setReplyText('');
      setWaitForCustomer(false);
      showToast(waitForCustomer ? 'Reply sent & SLA paused (Waiting on Customer)' : 'Reply sent to customer', 'success');
      loadTickets();
      loadTicketDetail(selectedTicketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Actions: Customer Reply (automatically resumes SLA)
  const handleCustomerReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!replyText.trim() || !selectedTicketId) return;

    try {
      await api.customerReply(activeCustomerId, selectedTicketId, replyText);
      setReplyText('');
      showToast('Reply submitted! (SLA resumed if previously waiting)', 'success');
      loadTickets();
      loadTicketDetail(selectedTicketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Actions: Add Internal Note (Strictly Agent Only)
  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!internalNoteText.trim() || !selectedTicketId) return;

    try {
      await api.addInternalNote(activeAgentId, selectedTicketId, internalNoteText);
      setInternalNoteText('');
      showToast('Internal note saved (Private to team only)', 'info');
      loadTicketDetail(selectedTicketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Actions: Update Priority or Status
  const handleUpdateStatus = async (status: string) => {
    if (!selectedTicketId) return;
    try {
      await api.updateTicket(activeAgentId, selectedTicketId, { status });
      showToast(`Status updated to ${status}`, 'success');
      loadTickets();
      loadTicketDetail(selectedTicketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  const handleUpdatePriority = async (priority: string) => {
    if (!selectedTicketId) return;
    try {
      await api.updateTicket(activeAgentId, selectedTicketId, { priority });
      showToast(`Priority escalated to ${priority} — SLA deadlines recalculated`, 'info');
      loadTickets();
      loadTicketDetail(selectedTicketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Actions: Customer Reopen
  const handleCustomerReopen = async (ticketId: number) => {
    try {
      const res = await api.customerReopen(activeCustomerId, ticketId);
      if (res.reopened) {
        showToast(res.message, 'success');
        loadTickets();
        setSelectedTicketId(res.ticket_id);
      } else {
        showToast(res.message, 'info');
        loadTickets();
        setSelectedTicketId(res.ticket_id);
      }
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Create Ticket
  const handleCreateTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubject.trim() || !newDescription.trim()) return;

    try {
      if (mode === 'AGENT') {
        const res = await api.createAgentTicket(activeAgentId, {
          customer_id: newTicketCustomerId,
          subject: newSubject,
          description: newDescription,
          priority: newPriority,
        });
        showToast(`Ticket ${res.ticket_number} created on behalf of customer!`, 'success');
        setShowNewTicketModal(false);
        loadTickets();
        setSelectedTicketId(res.id);
      } else {
        const res = await api.createCustomerTicket(activeCustomerId, {
          subject: newSubject,
          description: newDescription,
          priority: newPriority,
        });
        showToast(`Ticket ${res.ticket_number} created successfully!`, 'success');
        setShowNewTicketModal(false);
        loadTickets();
        setSelectedTicketId(res.id);
      }
      setNewSubject('');
      setNewDescription('');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Add Holiday
  const handleAddHoliday = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newHolidayDate || !newHolidayName.trim()) return;

    try {
      const added = await api.addHoliday(newHolidayDate, newHolidayName);
      setHolidays([...holidays, added]);
      setNewHolidayDate('');
      setNewHolidayName('');
      showToast(`Holiday "${added.name}" added to business calendar`, 'success');
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // Run Auto-Close Inactivity Trigger
  const handleRunAutoClose = async () => {
    try {
      const res = await api.triggerAutoClose();
      showToast(res.message, 'info');
      loadTickets();
      if (selectedTicketId) loadTicketDetail(selectedTicketId);
    } catch (err: any) {
      showToast(err.message, 'error');
    }
  };

  // KPI calculations
  const totalOpen = tickets.filter(t => t.status === 'OPEN' || t.status === 'IN_PROGRESS').length;
  const totalBreached = tickets.filter(t => t.sla?.is_breached).length;
  const totalWaiting = tickets.filter(t => t.status === 'WAITING_ON_CUSTOMER').length;
  const totalUnassigned = tickets.filter(t => !t.assignee_id).length;

  const currentAgent = agents.find(a => a.id === activeAgentId);
  const currentCustomer = customers.find(c => c.id === activeCustomerId);

  // Filter list by search query
  const filteredTickets = tickets.filter(t => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      t.ticket_number.toLowerCase().includes(q) ||
      t.subject.toLowerCase().includes(q) ||
      (t.customer_name && t.customer_name.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-slate-950 font-sans text-slate-100">
      {/* Toast Notification */}
      {toastMessage && (
        <div
          className={`fixed top-4 right-6 z-50 px-4 py-3 rounded-lg shadow-xl text-sm font-medium flex items-center space-x-2 border transition-all ${
            toastMessage.type === 'error'
              ? 'bg-rose-950/90 border-rose-500 text-rose-200'
              : toastMessage.type === 'success'
              ? 'bg-emerald-950/90 border-emerald-500 text-emerald-200'
              : 'bg-amber-950/90 border-amber-500 text-amber-200'
          }`}
        >
          {toastMessage.type === 'error' && <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0" />}
          {toastMessage.type === 'success' && <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />}
          {toastMessage.type === 'info' && <Clock className="w-5 h-5 text-amber-400 shrink-0" />}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Top Bar */}
      <header className="h-16 border-b border-slate-800 bg-slate-900/90 px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-black text-white shadow-md">
              FD
            </div>
            <div>
              <span className="font-bold text-base text-white tracking-tight">Frontdesk</span>
              <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                Arvo Systems
              </span>
            </div>
          </div>

          <div className="h-5 w-px bg-slate-800 mx-2" />

          {/* Mode Toggle Switcher */}
          <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-medium">
            <button
              onClick={() => { setMode('AGENT'); setSelectedTicketId(null); }}
              className={`px-3 py-1.5 rounded-md flex items-center space-x-1.5 transition-all ${
                mode === 'AGENT'
                  ? 'bg-indigo-600 text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>Agent Workspace</span>
            </button>
            <button
              onClick={() => { setMode('CUSTOMER'); setSelectedTicketId(null); }}
              className={`px-3 py-1.5 rounded-md flex items-center space-x-1.5 transition-all ${
                mode === 'CUSTOMER'
                  ? 'bg-emerald-600 text-white shadow-sm font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Customer Portal (Zero-Leak)</span>
            </button>
          </div>
        </div>

        {/* Right Switchers and Utility Controls */}
        <div className="flex items-center space-x-4">
          {mode === 'AGENT' ? (
            <div className="flex items-center space-x-2">
              <span className="text-xs text-slate-400 font-medium">Active Agent:</span>
              <select
                value={activeAgentId}
                onChange={(e) => setActiveAgentId(Number(e.target.value))}
                className="bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-medium"
              >
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.role})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className="flex items-center space-x-2">
              <span className="text-xs text-slate-400 font-medium">Simulated Customer:</span>
              <select
                value={activeCustomerId}
                onChange={(e) => setActiveCustomerId(Number(e.target.value))}
                className="bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-emerald-500 font-medium"
              >
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Quick Action Buttons */}
          <button
            onClick={() => setShowHolidaysModal(true)}
            className="text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2.5 py-1.5 rounded-md flex items-center space-x-1.5"
            title="View or Add Business Holidays"
          >
            <Calendar className="w-3.5 h-3.5" />
            <span>IST Holidays ({holidays.length})</span>
          </button>

          {mode === 'AGENT' && (
            <button
              onClick={handleRunAutoClose}
              className="text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 px-2.5 py-1.5 rounded-md flex items-center space-x-1.5"
              title="Trigger 5-day inactive auto-close check"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Run Auto-Close Scan</span>
            </button>
          )}

          <button
            onClick={() => setShowNewTicketModal(true)}
            className={`text-xs px-3 py-1.5 rounded-md font-semibold flex items-center space-x-1.5 shadow-sm text-white ${
              mode === 'AGENT' ? 'bg-indigo-600 hover:bg-indigo-500' : 'bg-emerald-600 hover:bg-emerald-500'
            }`}
          >
            <PlusCircle className="w-4 h-4" />
            <span>New Ticket</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Column: KPI Strip + Ticket Queue (38% width) */}
        <div className="w-[420px] lg:w-[480px] border-r border-slate-800 flex flex-col bg-slate-900/50 shrink-0">
          {/* KPI Strip (Agent Mode Only) */}
          {mode === 'AGENT' && (
            <div className="grid grid-cols-4 gap-2 p-3 border-b border-slate-800 bg-slate-900">
              <div className="bg-slate-950 p-2 rounded-md border border-slate-800 text-center">
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Open</span>
                <p className="text-base font-extrabold text-slate-100">{totalOpen}</p>
              </div>
              <div className="bg-rose-950/30 p-2 rounded-md border border-rose-900/50 text-center">
                <span className="text-[10px] text-rose-400 uppercase font-bold tracking-wider">Breached</span>
                <p className="text-base font-extrabold text-rose-300">{totalBreached}</p>
              </div>
              <div className="bg-amber-950/30 p-2 rounded-md border border-amber-900/50 text-center">
                <span className="text-[10px] text-amber-400 uppercase font-bold tracking-wider">Waiting</span>
                <p className="text-base font-extrabold text-amber-300">{totalWaiting}</p>
              </div>
              <div className="bg-slate-950 p-2 rounded-md border border-slate-800 text-center">
                <span className="text-[10px] text-indigo-400 uppercase font-bold tracking-wider">Unassigned</span>
                <p className="text-base font-extrabold text-indigo-300">{totalUnassigned}</p>
              </div>
            </div>
          )}

          {/* Filter Bar */}
          <div className="p-3 border-b border-slate-800 flex flex-col space-y-2 bg-slate-900/30">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search ticket #, subject, customer..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-md pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              />
            </div>

            {mode === 'AGENT' && (
              <div className="flex items-center justify-between text-xs pt-1">
                <div className="flex space-x-1">
                  {(['ALL', 'MY', 'UNASSIGNED', 'BREACHED', 'WAITING'] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setFilterType(tab)}
                      className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                        filterType === tab
                          ? 'bg-slate-800 text-white font-bold border border-slate-700'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {tab === 'MY' ? 'Mine' : tab === 'UNASSIGNED' ? 'Unassigned' : tab === 'BREACHED' ? 'Breached' : tab === 'WAITING' ? 'Waiting' : 'All'}
                    </button>
                  ))}
                </div>

                <select
                  value={priorityFilter}
                  onChange={(e) => setPriorityFilter(e.target.value)}
                  className="bg-slate-950 border border-slate-800 text-slate-400 text-[11px] rounded px-1.5 py-1 focus:outline-none"
                >
                  <option value="">Priority: All</option>
                  <option value="URGENT">Urgent</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="LOW">Low</option>
                </select>
              </div>
            )}
          </div>

          {/* Ticket List Queue */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
            {isLoading && tickets.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">Loading queue...</div>
            ) : filteredTickets.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">No tickets found.</div>
            ) : (
              filteredTickets.map((t) => {
                const isSelected = selectedTicketId === t.id;
                const isBreached = t.sla?.is_breached;
                const isPaused = t.status === 'WAITING_ON_CUSTOMER';
                const isUnassigned = !t.assignee_id;

                return (
                  <div
                    key={t.id}
                    onClick={() => setSelectedTicketId(t.id)}
                    className={`p-3.5 cursor-pointer transition-colors relative flex flex-col space-y-1.5 ${
                      isSelected
                        ? 'bg-slate-800/80 border-l-4 border-l-indigo-500'
                        : 'hover:bg-slate-900/60 border-l-4 border-l-transparent'
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center space-x-2">
                        <span className="font-mono font-bold text-slate-200">{t.ticket_number}</span>
                        {/* Priority Badge */}
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            t.priority === 'URGENT'
                              ? 'bg-rose-950 text-rose-400 border border-rose-800'
                              : t.priority === 'MEDIUM'
                              ? 'bg-amber-950 text-amber-400 border border-amber-800'
                              : 'bg-slate-800 text-slate-400 border border-slate-700'
                          }`}
                        >
                          {t.priority}
                        </span>
                      </div>

                      {/* Status / SLA Badges */}
                      <div className="flex items-center space-x-1.5">
                        {isBreached && (
                          <span className="bg-rose-600 text-white font-extrabold text-[9px] px-1.5 py-0.5 rounded flex items-center space-x-1 animate-pulse">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            <span>BREACHED</span>
                          </span>
                        )}
                        {isPaused && (
                          <span className="bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold text-[9px] px-1.5 py-0.5 rounded flex items-center space-x-1">
                            <Pause className="w-2.5 h-2.5" />
                            <span>PAUSED</span>
                          </span>
                        )}
                        <span
                          className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                            t.status === 'OPEN'
                              ? 'bg-indigo-950 text-indigo-300'
                              : t.status === 'IN_PROGRESS'
                              ? 'bg-sky-950 text-sky-300'
                              : t.status === 'RESOLVED'
                              ? 'bg-emerald-950 text-emerald-300'
                              : t.status === 'CLOSED'
                              ? 'bg-slate-800 text-slate-400'
                              : 'bg-amber-950 text-amber-300'
                          }`}
                        >
                          {t.status.replace(/_/g, ' ')}
                        </span>
                      </div>
                    </div>

                    <p className="text-xs font-semibold text-slate-100 line-clamp-1">{t.subject}</p>
                    <p className="text-[11px] text-slate-400 line-clamp-2">{t.description}</p>

                    <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1">
                      <span className="truncate max-w-[150px]">{t.customer_name || 'Customer'}</span>
                      <div className="flex items-center space-x-2">
                        {mode === 'AGENT' && (
                          <span>
                            {t.assignee_name ? (
                              <span className="text-slate-300">{t.assignee_name}</span>
                            ) : (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleClaim(t.id);
                                }}
                                className="px-2 py-0.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-bold tracking-tight shadow-sm"
                              >
                                Take Ticket
                              </button>
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Ticket Detail + Conversation Thread + Composer */}
        <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
          {ticketDetail ? (
            <>
              {/* Ticket Detail Header */}
              <div className="border-b border-slate-800 bg-slate-900/60 p-4 shrink-0 flex flex-col space-y-3">
                <div className="flex items-start justify-between">
                  <div className="flex flex-col space-y-1">
                    <div className="flex items-center space-x-3">
                      <span className="font-mono text-lg font-bold text-white">{ticketDetail.ticket_number}</span>
                      {ticketDetail.parent_ticket_id && (
                        <span className="text-[11px] font-semibold bg-purple-950 text-purple-300 border border-purple-800 px-2 py-0.5 rounded">
                          Follow-up to #{ticketDetail.parent_ticket_id}
                        </span>
                      )}
                      <span
                        className={`text-xs font-bold px-2 py-0.5 rounded ${
                          ticketDetail.priority === 'URGENT'
                            ? 'bg-rose-950 text-rose-300 border border-rose-800'
                            : ticketDetail.priority === 'MEDIUM'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {ticketDetail.priority}
                      </span>
                      <span className="text-xs text-slate-400">
                        Status: <strong className="text-slate-200">{ticketDetail.status}</strong>
                      </span>
                    </div>
                    <h1 className="text-base font-bold text-slate-100">{ticketDetail.subject}</h1>
                  </div>

                  {/* Header Actions */}
                  <div className="flex items-center space-x-2">
                    {mode === 'AGENT' ? (
                      <>
                        {/* Assignee / Claim Button */}
                        {!ticketDetail.assignee_id ? (
                          <button
                            onClick={() => handleClaim(ticketDetail.id)}
                            className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-3 py-1.5 rounded shadow-sm flex items-center space-x-1.5"
                          >
                            <UserCheck className="w-3.5 h-3.5" />
                            <span>Claim Ticket (INC-0291)</span>
                          </button>
                        ) : (
                          <div className="text-xs bg-slate-900 border border-slate-700 px-2.5 py-1.5 rounded text-slate-300 flex items-center space-x-1.5">
                            <UserCheck className="w-3.5 h-3.5 text-indigo-400" />
                            <span>Assigned: <strong>{ticketDetail.assignee_name}</strong></span>
                          </div>
                        )}

                        {/* Priority Escalation Dropdown */}
                        <select
                          value={ticketDetail.priority}
                          onChange={(e) => handleUpdatePriority(e.target.value)}
                          className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        >
                          <option value="URGENT">Priority: URGENT</option>
                          <option value="MEDIUM">Priority: MEDIUM</option>
                          <option value="LOW">Priority: LOW</option>
                        </select>

                        {/* Status Dropdown */}
                        <select
                          value={ticketDetail.status}
                          onChange={(e) => handleUpdateStatus(e.target.value)}
                          className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        >
                          <option value="OPEN">OPEN</option>
                          <option value="IN_PROGRESS">IN_PROGRESS</option>
                          <option value="WAITING_ON_CUSTOMER">WAITING_ON_CUSTOMER</option>
                          <option value="RESOLVED">RESOLVED</option>
                          <option value="CLOSED">CLOSED</option>
                        </select>
                      </>
                    ) : (
                      <>
                        {/* Customer Mode Actions: Reopen & Export */}
                        {(ticketDetail.status === 'RESOLVED' || ticketDetail.status === 'CLOSED') && (
                          <button
                            onClick={() => handleCustomerReopen(ticketDetail.id)}
                            className="bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold px-3 py-1.5 rounded flex items-center space-x-1.5 shadow-sm"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            <span>Reopen / Follow-up</span>
                          </button>
                        )}
                        <a
                          href={api.exportCustomerUrl(activeCustomerId, ticketDetail.id, 'json')}
                          target="_blank"
                          rel="noreferrer"
                          className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-2.5 py-1.5 rounded border border-slate-700 flex items-center space-x-1"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>Export JSON</span>
                        </a>
                        <a
                          href={api.exportCustomerUrl(activeCustomerId, ticketDetail.id, 'csv')}
                          target="_blank"
                          rel="noreferrer"
                          className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-2.5 py-1.5 rounded border border-slate-700 flex items-center space-x-1"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>Export CSV</span>
                        </a>
                      </>
                    )}
                  </div>
                </div>

                {/* SLA Breakdown Card (Agent Mode) */}
                {mode === 'AGENT' && ticketDetail.sla && (
                  <div className="bg-slate-950/80 p-2.5 rounded-lg border border-slate-800/80 grid grid-cols-4 gap-3 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">First Response Due</span>
                      <p className="font-mono text-slate-200">
                        {ticketDetail.first_response_due_at
                          ? new Date(ticketDetail.first_response_due_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })
                          : 'Responded'}
                      </p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">Resolution Due</span>
                      <p className="font-mono text-slate-200">
                        {ticketDetail.resolution_due_at
                          ? new Date(ticketDetail.resolution_due_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })
                          : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">Paused Working Time</span>
                      <p className="font-mono text-slate-200">{ticketDetail.total_paused_working_minutes} mins</p>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-semibold">SLA Status</span>
                      <p className="font-bold flex items-center space-x-1">
                        {ticketDetail.sla.is_breached ? (
                          <span className="text-rose-400 flex items-center space-x-1">
                            <AlertTriangle className="w-3 h-3" />
                            <span>Breached ({ticketDetail.sla.breach_type})</span>
                          </span>
                        ) : ticketDetail.sla.is_paused ? (
                          <span className="text-amber-400 flex items-center space-x-1">
                            <Pause className="w-3 h-3" />
                            <span>Paused</span>
                          </span>
                        ) : (
                          <span className="text-emerald-400 flex items-center space-x-1">
                            <CheckCircle2 className="w-3 h-3" />
                            <span>Within SLA Targets</span>
                          </span>
                        )}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Conversation Feed */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Initial Description Card */}
                <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
                  <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                    <span className="font-semibold text-slate-300">
                      {ticketDetail.customer_name || 'Customer'} (Original Ticket Description)
                    </span>
                    <span>{new Date(ticketDetail.created_at).toLocaleString()}</span>
                  </div>
                  <div className="text-xs text-slate-200 whitespace-pre-wrap">{ticketDetail.description}</div>
                </div>

                {/* Unified Public Messages & Internal Notes Feed */}
                {(() => {
                  const items: Array<{ type: 'MSG' | 'NOTE'; date: string; data: any }> = [];
                  (ticketDetail.public_messages || []).forEach(m => items.push({ type: 'MSG', date: m.created_at, data: m }));
                  (ticketDetail.internal_notes || []).forEach(n => items.push({ type: 'NOTE', date: n.created_at, data: n }));
                  items.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

                  return items.map((item, idx) => {
                    if (item.type === 'NOTE') {
                      // Internal Team Note (INC-0304): Amber tint, Lock Icon, Team-Only Banner
                      return (
                        <div
                          key={`note-${idx}`}
                          className="bg-amber-950/20 border-2 border-amber-600/50 rounded-lg p-3.5 shadow-sm"
                        >
                          <div className="flex items-center justify-between text-xs text-amber-400 mb-1.5 font-bold">
                            <div className="flex items-center space-x-2">
                              <Lock className="w-3.5 h-3.5 text-amber-500" />
                              <span className="uppercase text-[11px] tracking-wider bg-amber-950 px-2 py-0.5 rounded border border-amber-800 text-amber-300">
                                TEAM ONLY — NEVER SHOWN TO CUSTOMER (INC-0304)
                              </span>
                              <span className="text-slate-300 font-medium">by {item.data.author_name}</span>
                            </div>
                            <span className="text-slate-400 text-[11px]">{new Date(item.data.created_at).toLocaleString()}</span>
                          </div>
                          <div className="text-xs text-amber-100 whitespace-pre-wrap">{item.data.body}</div>
                        </div>
                      );
                    } else {
                      // Public Message
                      const isAgent = item.data.author_role === 'AGENT' || item.data.author_role === 'LEAD';
                      return (
                        <div
                          key={`msg-${idx}`}
                          className={`rounded-lg p-3.5 border ${
                            isAgent
                              ? 'bg-slate-900 border-indigo-900/50 ml-6'
                              : 'bg-slate-900/90 border-slate-800 mr-6'
                          }`}
                        >
                          <div className="flex items-center justify-between text-xs text-slate-400 mb-1.5">
                            <span className={`font-semibold ${isAgent ? 'text-indigo-300' : 'text-slate-200'}`}>
                              {item.data.author_name || (isAgent ? 'Support Agent' : 'Customer')}
                              {isAgent && <span className="ml-2 text-[10px] bg-indigo-950 text-indigo-400 px-1.5 py-0.5 rounded">Support</span>}
                            </span>
                            <span className="text-[11px]">{new Date(item.data.created_at).toLocaleString()}</span>
                          </div>
                          <div className="text-xs text-slate-200 whitespace-pre-wrap">{item.data.body}</div>
                        </div>
                      );
                    }
                  });
                })()}

                {/* Audit Trail Drawer / Tab (Agent Mode) */}
                {mode === 'AGENT' && activeTab === 'AUDIT' && (
                  <div className="mt-6 border-t border-slate-800 pt-4">
                    <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center space-x-1.5">
                      <History className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Immutable PostgreSQL Audit Trail (INC-0318)</span>
                    </h3>
                    <div className="space-y-2">
                      {(ticketDetail.audit_logs || []).map((log) => (
                        <div
                          key={log.id}
                          className="bg-slate-900/80 border border-slate-800 p-2.5 rounded text-xs flex items-start justify-between"
                        >
                          <div>
                            <div className="flex items-center space-x-2">
                              <span className="font-mono font-bold text-indigo-400">{log.action}</span>
                              <span className="text-slate-400">by {log.actor_name}</span>
                            </div>
                            {log.metadata && Object.keys(log.metadata).length > 0 && (
                              <pre className="text-[10px] text-slate-400 font-mono mt-1 bg-slate-950 p-1 rounded max-w-md overflow-x-auto">
                                {JSON.stringify(log.metadata, null, 2)}
                              </pre>
                            )}
                          </div>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {new Date(log.created_at).toLocaleString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Bottom Composer */}
              <div className="border-t border-slate-800 bg-slate-900/90 p-4 shrink-0">
                {mode === 'AGENT' ? (
                  <div>
                    {/* Composer Tab Switcher */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex space-x-2">
                        <button
                          onClick={() => setActiveTab('REPLY')}
                          className={`text-xs px-3 py-1.5 rounded-md font-semibold flex items-center space-x-1.5 transition-colors ${
                            activeTab === 'REPLY'
                              ? 'bg-indigo-600 text-white shadow-sm'
                              : 'text-slate-400 hover:text-white bg-slate-800'
                          }`}
                        >
                          <Send className="w-3 h-3" />
                          <span>Reply to Customer</span>
                        </button>
                        <button
                          onClick={() => setActiveTab('NOTE')}
                          className={`text-xs px-3 py-1.5 rounded-md font-semibold flex items-center space-x-1.5 transition-colors ${
                            activeTab === 'NOTE'
                              ? 'bg-amber-600 text-white shadow-sm'
                              : 'text-slate-400 hover:text-white bg-slate-800'
                          }`}
                        >
                          <Lock className="w-3 h-3 text-amber-300" />
                          <span>Add Internal Note (INC-0304)</span>
                        </button>
                        <button
                          onClick={() => setActiveTab('AUDIT')}
                          className={`text-xs px-3 py-1.5 rounded-md font-semibold flex items-center space-x-1.5 transition-colors ${
                            activeTab === 'AUDIT'
                              ? 'bg-slate-700 text-white'
                              : 'text-slate-400 hover:text-white bg-slate-800'
                          }`}
                        >
                          <History className="w-3 h-3" />
                          <span>Audit Trail ({ticketDetail.audit_logs?.length || 0})</span>
                        </button>
                      </div>
                    </div>

                    {activeTab === 'REPLY' && (
                      <form onSubmit={handleAgentReply} className="flex flex-col space-y-2">
                        <textarea
                          rows={3}
                          placeholder="Type your public response to the customer..."
                          value={replyText}
                          onChange={(e) => setReplyText(e.target.value)}
                          className="w-full bg-slate-950 border border-slate-800 rounded-md p-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                        />
                        <div className="flex items-center justify-between pt-1">
                          <label className="flex items-center space-x-2 text-xs text-amber-400 cursor-pointer select-none">
                            <input
                              type="checkbox"
                              checked={waitForCustomer}
                              onChange={(e) => setWaitForCustomer(e.target.checked)}
                              className="rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-0"
                            />
                            <span>Mark as "Waiting on Customer" & pause SLA timer (INC Working-Hours Rule)</span>
                          </label>
                          <button
                            type="submit"
                            className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-4 py-2 rounded shadow-sm flex items-center space-x-1.5"
                          >
                            <Send className="w-3.5 h-3.5" />
                            <span>Send Public Reply</span>
                          </button>
                        </div>
                      </form>
                    )}

                    {activeTab === 'NOTE' && (
                      <form onSubmit={handleAddNote} className="flex flex-col space-y-2">
                        <div className="bg-amber-950/30 border border-amber-800/60 rounded px-2.5 py-1 text-[11px] text-amber-300 flex items-center space-x-1.5">
                          <Lock className="w-3 h-3 text-amber-400" />
                          <span>Private Team Note: Encrypted and strictly excluded from customer views & exports.</span>
                        </div>
                        <textarea
                          rows={3}
                          placeholder="Type confidential internal team note (investigation logs, internal diagnostics)..."
                          value={internalNoteText}
                          onChange={(e) => setInternalNoteText(e.target.value)}
                          className="w-full bg-slate-950 border border-amber-800/80 rounded-md p-2.5 text-xs text-amber-100 placeholder-amber-500/50 focus:outline-none focus:border-amber-500"
                        />
                        <div className="flex justify-end pt-1">
                          <button
                            type="submit"
                            className="bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold px-4 py-2 rounded shadow-sm flex items-center space-x-1.5"
                          >
                            <Lock className="w-3.5 h-3.5" />
                            <span>Save Private Note</span>
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                ) : (
                  /* Customer Reply Composer */
                  <form onSubmit={handleCustomerReply} className="flex flex-col space-y-2">
                    <textarea
                      rows={3}
                      placeholder="Type your reply to Arvo Support..."
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-md p-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                    />
                    <div className="flex justify-between items-center pt-1">
                      <span className="text-[11px] text-emerald-400">
                        Customer Portal: Replying automatically resumes paused SLAs.
                      </span>
                      <button
                        type="submit"
                        className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold px-4 py-2 rounded shadow-sm flex items-center space-x-1.5"
                      >
                        <Send className="w-3.5 h-3.5" />
                        <span>Send Message</span>
                      </button>
                    </div>
                  </form>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-slate-500">
              <MessageSquare className="w-12 h-12 mb-3 stroke-[1.2]" />
              <p className="text-sm font-medium">Select a ticket from the queue to view details</p>
            </div>
          )}
        </div>
      </div>

      {/* New Ticket Modal */}
      {showNewTicketModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl">
            <h2 className="text-base font-bold text-white mb-4">
              {mode === 'AGENT' ? 'Create Ticket on Behalf of Customer' : 'Submit a New Support Ticket'}
            </h2>
            <form onSubmit={handleCreateTicket} className="space-y-4">
              {mode === 'AGENT' && (
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Select Customer</label>
                  <select
                    value={newTicketCustomerId}
                    onChange={(e) => setNewTicketCustomerId(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded-md p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                  >
                    {customers.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.email})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Subject</label>
                <input
                  type="text"
                  required
                  placeholder="Summary of the issue..."
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Priority</label>
                <select
                  value={newPriority}
                  onChange={(e: any) => setNewPriority(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="URGENT">URGENT (Customer cannot work at all — 2h response)</option>
                  <option value="MEDIUM">MEDIUM (4.5h response / 3 working days)</option>
                  <option value="LOW">LOW (Small questions — 1 day response / 1 week resolution)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">Description</label>
                <textarea
                  rows={4}
                  required
                  placeholder="Detailed description of the issue or error stack..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-md p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewTicketModal(false)}
                  className="px-4 py-2 rounded-md bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                >
                  Create Ticket
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Holidays Calendar Modal */}
      {showHolidaysModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-md w-full p-6 shadow-2xl">
            <h2 className="text-base font-bold text-white mb-2 flex items-center space-x-2">
              <Calendar className="w-4 h-4 text-indigo-400" />
              <span>IST Working Calendar & Festival Holidays</span>
            </h2>
            <p className="text-xs text-slate-400 mb-4">
              Working hours: 09:30 – 18:30 IST (Mon-Fri). Weekends and the dates below are excluded from SLA calculations.
            </p>

            {/* List */}
            <div className="max-h-48 overflow-y-auto space-y-1.5 mb-4 divide-y divide-slate-800">
              {holidays.map((h) => (
                <div key={h.id} className="pt-1.5 flex justify-between text-xs text-slate-300">
                  <span className="font-medium">{h.name}</span>
                  <span className="font-mono text-slate-400">{h.date}</span>
                </div>
              ))}
            </div>

            {/* Add Holiday Form */}
            <form onSubmit={handleAddHoliday} className="border-t border-slate-800 pt-3 space-y-3">
              <h3 className="text-xs font-bold text-slate-300">Add New Festival Holiday</h3>
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="date"
                  required
                  value={newHolidayDate}
                  onChange={(e) => setNewHolidayDate(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded p-1.5 text-xs text-slate-200 focus:outline-none"
                />
                <input
                  type="text"
                  required
                  placeholder="Holiday Name"
                  value={newHolidayName}
                  onChange={(e) => setNewHolidayName(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded p-1.5 text-xs text-slate-200 focus:outline-none"
                />
              </div>
              <div className="flex justify-between items-center pt-2">
                <button
                  type="button"
                  onClick={() => setShowHolidaysModal(false)}
                  className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 text-xs"
                >
                  Close
                </button>
                <button
                  type="submit"
                  className="px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
                >
                  Add Holiday
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
