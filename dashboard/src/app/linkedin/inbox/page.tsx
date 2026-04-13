"use client";

import { useEffect, useState } from "react";
import {
  getLinkedInConversations,
  getLinkedInConversation,
  submitLinkedInFeedback,
  approveLinkedInConversation,
  rejectLinkedInConversation,
  syncLinkedInConversations,
  type LinkedInConversation,
  type LinkedInConversationDetail,
} from "@/lib/api";

const categoryStyles: Record<string, { bg: string; color: string; label: string }> = {
  interested: { bg: "#eef2ff", color: "#3366FF", label: "Interested" },
  not_interested: { bg: "#fef2f2", color: "#ef4444", label: "Not Interested" },
  info_request: { bg: "#eef2ff", color: "#6366f1", label: "Info Request" },
  referral: { bg: "#fffbeb", color: "#d97706", label: "Referral" },
  wrong_person: { bg: "#f5f3ff", color: "#8b5cf6", label: "Wrong Person" },
  out_of_office: { bg: "#f3f4f6", color: "#6b7280", label: "OOO" },
  already_client: { bg: "#f0fdf4", color: "#16a34a", label: "Already Client" },
};

const statusStyles: Record<string, { bg: string; color: string; label: string }> = {
  pending_approval: { bg: "#fff7ed", color: "#ea580c", label: "Pending" },
  approved: { bg: "#eef2ff", color: "#3366FF", label: "Approved" },
  sent: { bg: "#f0fdf4", color: "#16a34a", label: "Sent" },
  rejected: { bg: "#fef2f2", color: "#ef4444", label: "Rejected" },
  auto_handled: { bg: "#f3f4f6", color: "#6b7280", label: "Auto" },
};

export default function LinkedInInboxPage() {
  const [conversations, setConversations] = useState<LinkedInConversation[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<LinkedInConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackHistory, setFeedbackHistory] = useState<{ feedback: string; revisedDraft: string }[]>([]);
  const [approveLoading, setApproveLoading] = useState(false);
  const [rejectLoading, setRejectLoading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    setLoading(true);
    getLinkedInConversations(page, categoryFilter || undefined, statusFilter || undefined)
      .then((data) => {
        setConversations(data.conversations);
        setTotalPages(data.pages);
        setTotal(data.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [page, categoryFilter, statusFilter]);

  useEffect(() => {
    setFeedbackText("");
    setFeedbackHistory([]);
    setActionError("");
    setDetail(null);
    if (selectedId) {
      setDetailLoading(true);
      getLinkedInConversation(selectedId)
        .then(setDetail)
        .catch(() => {})
        .finally(() => setDetailLoading(false));
    }
  }, [selectedId]);

  async function handleSync() {
    setSyncing(true);
    try {
      await syncLinkedInConversations();
      const data = await getLinkedInConversations(1, categoryFilter || undefined, statusFilter || undefined);
      setConversations(data.conversations);
      setTotalPages(data.pages);
      setTotal(data.total);
      setPage(1);
    } catch {
      // silent
    } finally {
      setSyncing(false);
    }
  }

  async function handleApprove() {
    if (!selectedId) return;
    setApproveLoading(true);
    setActionError("");
    try {
      const result = await approveLinkedInConversation(selectedId);
      setConversations((prev) =>
        prev.map((c) => (c.id === selectedId ? { ...c, status: "sent", sent_at: result.sent_at } : c))
      );
      if (detail) setDetail({ ...detail, status: "sent", sent_at: result.sent_at });
    } catch (err: unknown) {
      setActionError(`Failed to send: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setApproveLoading(false);
    }
  }

  async function handleReject() {
    if (!selectedId) return;
    setRejectLoading(true);
    try {
      await rejectLinkedInConversation(selectedId);
      setConversations((prev) =>
        prev.map((c) => (c.id === selectedId ? { ...c, status: "rejected" } : c))
      );
      if (detail) setDetail({ ...detail, status: "rejected" });
    } catch {
      // silent
    } finally {
      setRejectLoading(false);
    }
  }

  async function handleFeedbackSubmit() {
    if (!feedbackText.trim() || !selectedId) return;
    setFeedbackLoading(true);
    try {
      const result = await submitLinkedInFeedback(selectedId, feedbackText.trim());
      setFeedbackHistory((prev) => [
        ...prev,
        { feedback: feedbackText.trim(), revisedDraft: result.draft_response },
      ]);
      setConversations((prev) =>
        prev.map((c) => (c.id === selectedId ? { ...c, draft_response: result.draft_response } : c))
      );
      if (detail) setDetail({ ...detail, draft_response: result.draft_response });
      setFeedbackText("");
    } catch {
      // silent
    } finally {
      setFeedbackLoading(false);
    }
  }

  const selectedConv = conversations.find((c) => c.id === selectedId);

  return (
    <div className="flex gap-0" style={{ height: "calc(100vh - 64px)" }}>
      {/* Left panel */}
      <div
        className="flex flex-col overflow-hidden rounded-2xl bg-white"
        style={{
          border: "1px solid #e2e6ee",
          width: selectedId ? "420px" : "100%",
          minWidth: "420px",
          transition: "width 0.2s ease",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid #e2e6ee" }}>
          <div>
            <h1 className="text-[15px] font-semibold" style={{ color: "#1a1a2e" }}>
              LinkedIn Inbox
            </h1>
            <p className="text-[11px]" style={{ color: "#a5abbe" }}>
              {total} conversations
            </p>
          </div>
          <div className="flex gap-2">
            <select
              value={categoryFilter}
              onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); setSelectedId(null); }}
              className="rounded-lg bg-transparent px-2 py-1.5 text-[11px] font-medium outline-none"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              <option value="">All Categories</option>
              <option value="interested">Interested</option>
              <option value="not_interested">Not Interested</option>
              <option value="info_request">Info Request</option>
              <option value="referral">Referral</option>
              <option value="wrong_person">Wrong Person</option>
              <option value="out_of_office">OOO</option>
              <option value="already_client">Already Client</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value); setPage(1); setSelectedId(null); }}
              className="rounded-lg bg-transparent px-2 py-1.5 text-[11px] font-medium outline-none"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              <option value="">All Statuses</option>
              <option value="pending_approval">Pending</option>
              <option value="sent">Sent</option>
              <option value="rejected">Rejected</option>
              <option value="auto_handled">Auto</option>
            </select>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="rounded-lg px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-60"
              style={{ backgroundColor: "#0A66C2" }}
            >
              {syncing ? "..." : "Sync"}
            </button>
          </div>
        </div>

        {/* Conversation rows */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <div
                className="h-6 w-6 animate-spin rounded-full border-[2.5px] border-[#e2e6ee]"
                style={{ borderTopColor: "#0A66C2" }}
              />
            </div>
          ) : conversations.length === 0 ? (
            <div className="flex h-40 flex-col items-center justify-center gap-2 text-[13px]" style={{ color: "#a5abbe" }}>
              <span>No conversations found</span>
              <button
                onClick={handleSync}
                className="rounded-lg px-4 py-2 text-[12px] font-semibold text-white"
                style={{ backgroundColor: "#0A66C2" }}
              >
                Sync from HeyReach
              </button>
            </div>
          ) : (
            conversations.map((c) => {
              const catStyle = categoryStyles[c.category] || { bg: "#f3f4f6", color: "#6b7280", label: c.category };
              const isActive = selectedId === c.id;

              return (
                <div
                  key={c.id}
                  onClick={() => setSelectedId(isActive ? null : c.id)}
                  className="flex cursor-pointer items-center gap-3 px-5 py-3 transition-colors"
                  style={{
                    borderBottom: "1px solid #f0f2f7",
                    backgroundColor: isActive ? "#e8f0fa" : "transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "#f8f9fc";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  {/* Category tag */}
                  <span
                    className="shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                    style={{ backgroundColor: catStyle.bg, color: catStyle.color, minWidth: "56px", textAlign: "center" }}
                  >
                    {catStyle.label}
                  </span>

                  {/* Lead info + preview */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="truncate text-[13px] font-semibold"
                        style={{ color: "#1a1a2e", maxWidth: selectedId ? "140px" : "240px" }}
                      >
                        {c.lead_name || "Unknown"}
                      </span>
                      <span className="truncate text-[12px] font-medium" style={{ color: "#5a6176" }}>
                        {c.last_message.slice(0, 55)}...
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px]" style={{ color: "#a5abbe" }}>
                      {c.lead_title ? `${c.lead_title}${c.lead_company ? " · " + c.lead_company : ""}` : c.lead_company}
                    </p>
                  </div>

                  {/* Time + status */}
                  <div className="shrink-0 text-right">
                    <p className="text-[11px] font-medium" style={{ color: "#a5abbe" }}>
                      {new Date(c.created_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        timeZone: "America/New_York",
                      })}
                    </p>
                    {c.status !== "auto_handled" && (
                      <span
                        className="mt-0.5 inline-block rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor: (statusStyles[c.status] || statusStyles.auto_handled).bg,
                          color: (statusStyles[c.status] || statusStyles.auto_handled).color,
                        }}
                      >
                        {(statusStyles[c.status] || statusStyles.auto_handled).label}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3" style={{ borderTop: "1px solid #e2e6ee" }}>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="rounded-lg px-3 py-1.5 text-[11px] font-medium disabled:opacity-40"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              Previous
            </button>
            <span className="text-[11px]" style={{ color: "#a5abbe" }}>
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="rounded-lg px-3 py-1.5 text-[11px] font-medium disabled:opacity-40"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Right panel — detail */}
      {selectedId && (
        <div
          className="flex flex-1 flex-col overflow-hidden rounded-2xl bg-white"
          style={{ border: "1px solid #e2e6ee", marginLeft: "12px" }}
        >
          {detailLoading ? (
            <div className="flex h-full items-center justify-center">
              <div
                className="h-8 w-8 animate-spin rounded-full border-[3px] border-[#e2e6ee]"
                style={{ borderTopColor: "#0A66C2" }}
              />
            </div>
          ) : detail ? (
            <>
              {/* Detail header */}
              <div className="px-6 py-4" style={{ borderBottom: "1px solid #e2e6ee" }}>
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-[15px] font-semibold" style={{ color: "#1a1a2e" }}>
                      {detail.lead_name}
                    </h2>
                    {(detail.lead_title || detail.lead_company) && (
                      <p className="mt-0.5 text-[12px]" style={{ color: "#a5abbe" }}>
                        {detail.lead_title}{detail.lead_title && detail.lead_company ? " · " : ""}{detail.lead_company}
                      </p>
                    )}
                    {detail.lead_linkedin_url && (
                      <a
                        href={detail.lead_linkedin_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-block text-[11px] font-medium"
                        style={{ color: "#0A66C2" }}
                      >
                        View LinkedIn Profile →
                      </a>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {selectedConv && (
                      <span
                        className="rounded-md px-2 py-1 text-[10px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor: (categoryStyles[selectedConv.category] || { bg: "#f3f4f6" }).bg,
                          color: (categoryStyles[selectedConv.category] || { color: "#6b7280" }).color,
                        }}
                      >
                        {(categoryStyles[selectedConv.category] || { label: selectedConv.category }).label}
                      </span>
                    )}
                    <button
                      onClick={() => setSelectedId(null)}
                      className="rounded-lg px-3 py-1.5 text-[11px] font-medium"
                      style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex flex-1 overflow-hidden">
                {/* Thread */}
                <div className="flex w-1/2 flex-col overflow-y-auto p-4" style={{ borderRight: "1px solid #e2e6ee" }}>
                  <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
                    Conversation Thread
                  </p>
                  {detail.thread.length === 0 ? (
                    <div className="rounded-xl p-4" style={{ backgroundColor: "#f8f9fc" }}>
                      <p className="text-[12px] font-medium" style={{ color: "#1a1a2e" }}>
                        Latest message:
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-[12px]" style={{ color: "#5a6176" }}>
                        {detail.last_message}
                      </p>
                    </div>
                  ) : (
                    detail.thread.map((msg, i) => (
                      <div
                        key={i}
                        className={`mb-3 max-w-[90%] rounded-xl px-4 py-3 ${msg.is_outgoing ? "self-end" : "self-start"}`}
                        style={{
                          backgroundColor: msg.is_outgoing ? "#e8f0fa" : "#f8f9fc",
                          border: "1px solid #e2e6ee",
                        }}
                      >
                        <p className="mb-1 text-[9px] font-semibold uppercase tracking-wider" style={{ color: "#a5abbe" }}>
                          {msg.is_outgoing ? "You" : detail.lead_name} · {new Date(msg.sent_at).toLocaleString("en-US", { timeZone: "America/New_York" })}
                        </p>
                        <p className="whitespace-pre-wrap text-[12px]" style={{ color: "#1a1a2e" }}>
                          {msg.content}
                        </p>
                      </div>
                    ))
                  )}
                </div>

                {/* Draft + actions */}
                <div className="flex w-1/2 flex-col overflow-y-auto p-4">
                  <p className="mb-3 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
                    AI Draft Reply
                  </p>

                  {/* Status banner */}
                  {detail.status === "sent" ? (
                    <div className="mb-3 rounded-xl px-4 py-3 text-[12px]" style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}>
                      Message sent via HeyReach
                      {detail.sent_at && ` · ${new Date(detail.sent_at).toLocaleString("en-US", { timeZone: "America/New_York" })}`}
                    </div>
                  ) : detail.status === "rejected" ? (
                    <div className="mb-3 rounded-xl px-4 py-3 text-[12px]" style={{ backgroundColor: "#fef2f2", color: "#ef4444" }}>
                      Rejected
                    </div>
                  ) : null}

                  {/* Draft */}
                  {detail.draft_response ? (
                    <div
                      className="mb-4 rounded-xl p-4 text-[12px]"
                      style={{ backgroundColor: "#f8f9fc", border: "1px solid #e2e6ee", color: "#1a1a2e", whiteSpace: "pre-wrap" }}
                    >
                      {feedbackHistory.length > 0
                        ? feedbackHistory[feedbackHistory.length - 1].revisedDraft
                        : detail.draft_response}
                    </div>
                  ) : (
                    <div className="mb-4 rounded-xl p-4 text-[12px]" style={{ backgroundColor: "#f8f9fc", color: "#a5abbe" }}>
                      No draft generated for this category.
                    </div>
                  )}

                  {/* Approve / Reject */}
                  {detail.status === "pending_approval" && detail.draft_response && (
                    <>
                      {actionError && (
                        <div className="mb-3 rounded-xl px-4 py-2 text-[11px]" style={{ backgroundColor: "#fef2f2", color: "#ef4444" }}>
                          {actionError}
                        </div>
                      )}
                      <div className="mb-4 flex gap-2">
                        <button
                          onClick={handleApprove}
                          disabled={approveLoading}
                          className="flex-1 rounded-xl py-2.5 text-[12px] font-semibold text-white disabled:opacity-60"
                          style={{ backgroundColor: "#0A66C2" }}
                        >
                          {approveLoading ? "Sending..." : "Approve & Send"}
                        </button>
                        <button
                          onClick={handleReject}
                          disabled={rejectLoading}
                          className="rounded-xl px-4 py-2.5 text-[12px] font-semibold disabled:opacity-60"
                          style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
                        >
                          {rejectLoading ? "..." : "Reject"}
                        </button>
                      </div>
                    </>
                  )}

                  {/* Feedback history */}
                  {feedbackHistory.length > 0 && (
                    <div className="mb-4">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
                        Revision History
                      </p>
                      {feedbackHistory.map((f, i) => (
                        <div key={i} className="mb-2 rounded-xl p-3 text-[11px]" style={{ backgroundColor: "#fffbeb", border: "1px solid #fde68a" }}>
                          <p className="font-semibold" style={{ color: "#d97706" }}>Feedback:</p>
                          <p style={{ color: "#92400e" }}>{f.feedback}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Feedback input */}
                  {detail.draft_response && detail.status !== "sent" && (
                    <div>
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
                        Request revision
                      </p>
                      <textarea
                        value={feedbackText}
                        onChange={(e) => setFeedbackText(e.target.value)}
                        placeholder="e.g. Make it shorter, mention their industry..."
                        rows={3}
                        className="w-full resize-none rounded-xl p-3 text-[12px] outline-none"
                        style={{ border: "1px solid #e2e6ee", color: "#1a1a2e" }}
                      />
                      <button
                        onClick={handleFeedbackSubmit}
                        disabled={feedbackLoading || !feedbackText.trim()}
                        className="mt-2 w-full rounded-xl py-2 text-[12px] font-semibold text-white disabled:opacity-50"
                        style={{ backgroundColor: "#3366FF" }}
                      >
                        {feedbackLoading ? "Revising..." : "Revise Draft"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
