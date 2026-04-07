"use client";

import { useEffect, useState } from "react";
import { getReplies, submitFeedback, approveReply, rejectReply, getReplyThread, type ReplyItem, type ThreadEmail } from "@/lib/api";

function stripHtml(html: string): string {
  if (!html) return "";
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/div>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<\/li>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const categoryStyles: Record<string, { bg: string; color: string; label: string }> = {
  interested: { bg: "#eef2ff", color: "#3366FF", label: "Interested" },
  not_interested: { bg: "#fef2f2", color: "#ef4444", label: "Not Interested" },
  ooo: { bg: "#fffbeb", color: "#d97706", label: "OOO" },
  unsubscribe: { bg: "#f3f4f6", color: "#6b7280", label: "Unsubscribe" },
  info_request: { bg: "#eef2ff", color: "#6366f1", label: "Info Request" },
  wrong_person: { bg: "#f5f3ff", color: "#8b5cf6", label: "Wrong Person" },
  dnc: { bg: "#fef2f2", color: "#dc2626", label: "DNC" },
};

const statusStyles: Record<string, { bg: string; color: string; label: string }> = {
  pending_approval: { bg: "#fff7ed", color: "#ea580c", label: "Pending" },
  approved: { bg: "#eef2ff", color: "#3366FF", label: "Approved" },
  sent: { bg: "#f0fdf4", color: "#16a34a", label: "Sent" },
  rejected: { bg: "#fef2f2", color: "#ef4444", label: "Rejected" },
  auto_handled: { bg: "#f3f4f6", color: "#6b7280", label: "Auto" },
  human_managed: { bg: "#eef2ff", color: "#6366f1", label: "Human" },
  needs_josh: { bg: "#fff7ed", color: "#ea580c", label: "Needs Josh" },
};

export default function RepliesPage() {
  const [replies, setReplies] = useState<ReplyItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackHistory, setFeedbackHistory] = useState<
    { feedback: string; revisedDraft: string }[]
  >([]);
  const [approveLoading, setApproveLoading] = useState(false);
  const [rejectLoading, setRejectLoading] = useState(false);
  const [actionError, setActionError] = useState("");
  const [thread, setThread] = useState<ThreadEmail[]>([]);
  const [threadLoading, setThreadLoading] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getReplies(
          page,
          categoryFilter || undefined,
          statusFilter || undefined
        );
        setReplies(data.replies);
        setTotalPages(data.pages);
        setTotal(data.total);
      } catch {
        // API not available yet
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page, categoryFilter, statusFilter]);

  // Reset feedback state and fetch thread when selecting a different reply
  useEffect(() => {
    setFeedbackText("");
    setFeedbackHistory([]);
    setThread([]);
    setActionError("");
    if (selectedId) {
      setThreadLoading(true);
      getReplyThread(selectedId)
        .then((data) => setThread(data.thread))
        .catch(() => {})
        .finally(() => setThreadLoading(false));
    }
  }, [selectedId]);

  async function handleApprove() {
    if (!selectedId) return;
    setApproveLoading(true);
    setActionError("");
    try {
      const result = await approveReply(selectedId);
      setReplies((prev) =>
        prev.map((r) =>
          r.id === selectedId
            ? { ...r, status: "sent", sent_at: result.sent_at }
            : r
        )
      );
    } catch (err) {
      setActionError("Failed to send reply. Check Instantly API key or try again.");
    } finally {
      setApproveLoading(false);
    }
  }

  async function handleReject() {
    if (!selectedId) return;
    setRejectLoading(true);
    try {
      await rejectReply(selectedId);
      setReplies((prev) =>
        prev.map((r) =>
          r.id === selectedId ? { ...r, status: "rejected" } : r
        )
      );
    } catch {
      // handle error silently
    } finally {
      setRejectLoading(false);
    }
  }

  async function handleFeedbackSubmit() {
    if (!feedbackText.trim() || !selectedId) return;
    setFeedbackLoading(true);
    try {
      const result = await submitFeedback(selectedId, feedbackText.trim());
      setFeedbackHistory((prev) => [
        ...prev,
        { feedback: feedbackText.trim(), revisedDraft: result.draft_response },
      ]);
      // Update the reply in the list so the latest draft is shown
      setReplies((prev) =>
        prev.map((r) =>
          r.id === selectedId ? { ...r, draft_response: result.draft_response } : r
        )
      );
      setFeedbackText("");
    } catch {
      // handle error silently
    } finally {
      setFeedbackLoading(false);
    }
  }

  const selectedReply = replies.find((r) => r.id === selectedId);

  return (
    <div className="flex gap-0" style={{ height: "calc(100vh - 64px)" }}>
      {/* Left panel — inbox list */}
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
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid #e2e6ee" }}
        >
          <div>
            <h1 className="text-[15px] font-semibold" style={{ color: "#1a1a2e" }}>
              Inbox
            </h1>
            <p className="text-[11px]" style={{ color: "#a5abbe" }}>
              {total} replies
            </p>
          </div>
          <div className="flex gap-2">
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
                setSelectedId(null);
              }}
              className="rounded-lg bg-transparent px-2 py-1.5 text-[11px] font-medium outline-none"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              <option value="">All Categories</option>
              <option value="interested">Interested</option>
              <option value="not_interested">Not Interested</option>
              <option value="ooo">OOO</option>
              <option value="unsubscribe">Unsubscribe</option>
              <option value="info_request">Info Request</option>
              <option value="wrong_person">Wrong Person</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
                setSelectedId(null);
              }}
              className="rounded-lg bg-transparent px-2 py-1.5 text-[11px] font-medium outline-none"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              <option value="">All Statuses</option>
              <option value="pending_approval">Pending</option>
              <option value="sent">Sent</option>
              <option value="rejected">Rejected</option>
              <option value="auto_handled">Auto</option>
            </select>
          </div>
        </div>

        {/* Reply rows */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <div
                className="h-6 w-6 animate-spin rounded-full border-[2.5px] border-[#e2e6ee]"
                style={{ borderTopColor: "#3366FF" }}
              />
            </div>
          ) : replies.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
              No replies found
            </div>
          ) : (
            replies.map((r) => {
              const catStyle = categoryStyles[r.category] || { bg: "#f3f4f6", color: "#6b7280", label: r.category };
              const isActive = selectedId === r.id;

              return (
                <div
                  key={r.id}
                  onClick={() => setSelectedId(isActive ? null : r.id)}
                  className="flex cursor-pointer items-center gap-3 px-5 py-3 transition-colors"
                  style={{
                    borderBottom: "1px solid #f0f2f7",
                    backgroundColor: isActive ? "#f0f4ff" : "transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "#f8f9fc";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  {/* Category tag — left side */}
                  <span
                    className="shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                    style={{ backgroundColor: catStyle.bg, color: catStyle.color, minWidth: "56px", textAlign: "center" }}
                  >
                    {catStyle.label}
                  </span>

                  {/* Email + preview */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="truncate text-[13px] font-semibold"
                        style={{ color: "#1a1a2e", maxWidth: selectedId ? "140px" : "240px" }}
                      >
                        {r.lead_email.split("@")[0]}
                      </span>
                      <span className="truncate text-[12px] font-medium" style={{ color: "#5a6176" }}>
                        {r.reply_body.slice(0, 60)}...
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px]" style={{ color: "#a5abbe" }}>
                      {r.campaign_name}
                    </p>
                  </div>

                  {/* Time + status */}
                  <div className="shrink-0 text-right">
                    <p className="text-[11px] font-medium" style={{ color: "#a5abbe" }}>
                      {new Date(r.received_at).toLocaleTimeString("en-US", {
                        hour: "numeric",
                        minute: "2-digit",
                        hour12: true,
                        timeZone: "America/New_York",
                      })}
                    </p>
                    {r.status !== "auto_handled" && (
                      <span
                        className="mt-0.5 inline-block rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor: (statusStyles[r.status] || statusStyles.auto_handled).bg,
                          color: (statusStyles[r.status] || statusStyles.auto_handled).color,
                        }}
                      >
                        {(statusStyles[r.status] || statusStyles.auto_handled).label}
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
          <div
            className="flex items-center justify-between px-5 py-3"
            style={{ borderTop: "1px solid #e2e6ee" }}
          >
            <button
              onClick={() => { setPage((p) => Math.max(1, p - 1)); setSelectedId(null); }}
              disabled={page === 1}
              className="text-[11px] font-medium disabled:opacity-30"
              style={{ color: "#5a6176" }}
            >
              &larr; Prev
            </button>
            <span className="text-[11px] font-medium" style={{ color: "#a5abbe" }}>
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => { setPage((p) => Math.min(totalPages, p + 1)); setSelectedId(null); }}
              disabled={page === totalPages}
              className="text-[11px] font-medium disabled:opacity-30"
              style={{ color: "#5a6176" }}
            >
              Next &rarr;
            </button>
          </div>
        )}
      </div>

      {/* Right panel — conversation detail */}
      {selectedId && selectedReply && (
        <div
          className="ml-5 flex flex-1 flex-col overflow-hidden rounded-2xl bg-white"
          style={{ border: "1px solid #e2e6ee" }}
        >
          {/* Detail header */}
          <div
            className="flex items-center justify-between px-6 py-4"
            style={{ borderBottom: "1px solid #e2e6ee" }}
          >
            <div>
              <h2 className="text-[15px] font-semibold" style={{ color: "#1a1a2e" }}>
                {selectedReply.lead_email}
              </h2>
              <p className="mt-0.5 text-[11px]" style={{ color: "#a5abbe" }}>
                {selectedReply.campaign_name} &middot;{" "}
                {new Date(selectedReply.received_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                  timeZone: "America/New_York",
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
                style={{
                  backgroundColor: (categoryStyles[selectedReply.category] || categoryStyles.interested).bg,
                  color: (categoryStyles[selectedReply.category] || categoryStyles.interested).color,
                }}
              >
                {(categoryStyles[selectedReply.category] || { label: selectedReply.category }).label}
              </span>
              <span
                className="rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
                style={{
                  backgroundColor: (statusStyles[selectedReply.status] || statusStyles.auto_handled).bg,
                  color: (statusStyles[selectedReply.status] || statusStyles.auto_handled).color,
                }}
              >
                {(statusStyles[selectedReply.status] || statusStyles.auto_handled).label}
              </span>
              <button
                onClick={() => setSelectedId(null)}
                className="ml-2 rounded-lg p-1.5 transition-colors hover:bg-[#f5f7fa]"
              >
                <svg className="h-4 w-4" fill="none" stroke="#8a91a5" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Conversation thread */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {threadLoading ? (
              <div className="flex h-20 items-center justify-center">
                <div
                  className="h-5 w-5 animate-spin rounded-full border-[2.5px] border-[#e2e6ee]"
                  style={{ borderTopColor: "#3366FF" }}
                />
                <span className="ml-3 text-[12px]" style={{ color: "#a5abbe" }}>
                  Loading conversation...
                </span>
              </div>
            ) : thread.length > 0 ? (
              <>
                {/* Full thread from Instantly.ai */}
                {thread.map((email, idx) => {
                  const isSent = email.type === "sent";
                  return (
                    <div key={email.id || idx} className="mb-6">
                      <div className="mb-2 flex items-center gap-2">
                        <div
                          className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white"
                          style={{ backgroundColor: isSent ? "#16a34a" : "#3366FF" }}
                        >
                          {isSent ? (
                            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            (email.from || selectedReply.lead_email).charAt(0).toUpperCase()
                          )}
                        </div>
                        <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                          {isSent ? "You" : (email.from || selectedReply.lead_email)}
                        </span>
                        <span
                          className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                          style={
                            isSent
                              ? { backgroundColor: "#f0fdf4", color: "#16a34a" }
                              : { backgroundColor: "#eef2ff", color: "#3366FF" }
                          }
                        >
                          {isSent ? "Sent" : "Received"}
                        </span>
                        {email.timestamp && (
                          <span className="text-[11px]" style={{ color: "#a5abbe" }}>
                            {new Date(email.timestamp).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                              timeZone: "America/New_York",
                            })}
                          </span>
                        )}
                      </div>
                      <div
                        className="ml-9 rounded-xl p-4"
                        style={
                          isSent
                            ? { backgroundColor: "#f0fdf4", border: "1px solid #bbf7d0" }
                            : { backgroundColor: "#f8f9fc", border: "1px solid #eef1f6" }
                        }
                      >
                        <p className="text-[13px] leading-relaxed whitespace-pre-wrap" style={{ color: isSent ? "#166534" : "#3d4254" }}>
                          {stripHtml(email.body || email.content_preview || "(No content)")}
                        </p>
                      </div>
                    </div>
                  );
                })}

                {/* AI Draft — show below thread if pending */}
                {selectedReply.draft_response && selectedReply.status !== "sent" && (
                  <div className="mb-6">
                    <div className="mt-4 flex items-center gap-2">
                      <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
                      <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "#a5abbe" }}>
                        AI Draft
                      </span>
                      <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
                    </div>
                    <div className="mt-4">
                      <div className="mb-2 flex items-center gap-2">
                        <div
                          className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                          style={{ backgroundColor: "#eef2ff", color: "#3366FF" }}
                        >
                          AI
                        </div>
                        <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                          AI Draft Response
                        </span>
                        <span
                          className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                          style={{ backgroundColor: "#fffbeb", color: "#d97706" }}
                        >
                          Draft
                        </span>
                      </div>
                      <div
                        className="ml-9 rounded-xl p-4"
                        style={{ backgroundColor: "#f0f4ff", border: "1px solid #dde4f8" }}
                      >
                        <p className="text-[13px] leading-relaxed whitespace-pre-wrap" style={{ color: "#2d3a6e" }}>
                          {selectedReply.draft_response}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <>
                {/* Fallback: show single reply + draft if thread fetch failed */}
                <div className="mb-6">
                  <div className="mb-2 flex items-center gap-2">
                    <div
                      className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white"
                      style={{ backgroundColor: "#3366FF" }}
                    >
                      {selectedReply.lead_email.charAt(0).toUpperCase()}
                    </div>
                    <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                      {selectedReply.lead_email}
                    </span>
                    <span className="text-[11px]" style={{ color: "#a5abbe" }}>
                      {new Date(selectedReply.received_at).toLocaleTimeString("en-US", {
                        hour: "numeric",
                        minute: "2-digit",
                        hour12: true,
                        timeZone: "America/New_York",
                      })}
                    </span>
                  </div>
                  <div
                    className="ml-9 rounded-xl p-4"
                    style={{ backgroundColor: "#f8f9fc", border: "1px solid #eef1f6" }}
                  >
                    <p className="text-[13px] leading-relaxed" style={{ color: "#3d4254" }}>
                      {selectedReply.reply_body}
                    </p>
                  </div>
                </div>

                {selectedReply.draft_response && (
                  <div>
                    <div className="mb-2 flex items-center gap-2">
                      <div
                        className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                        style={{ backgroundColor: "#eef2ff", color: "#3366FF" }}
                      >
                        AI
                      </div>
                      <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                        {selectedReply.status === "sent" ? "Sent Response" : "AI Draft Response"}
                      </span>
                      <span
                        className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                        style={
                          selectedReply.status === "sent"
                            ? { backgroundColor: "#f0fdf4", color: "#16a34a" }
                            : { backgroundColor: "#fffbeb", color: "#d97706" }
                        }
                      >
                        {selectedReply.status === "sent" ? "Sent" : "Draft"}
                      </span>
                    </div>
                    <div
                      className="ml-9 rounded-xl p-4"
                      style={{ backgroundColor: "#f0f4ff", border: "1px solid #dde4f8" }}
                    >
                      <p className="text-[13px] leading-relaxed" style={{ color: "#2d3a6e" }}>
                        {selectedReply.draft_response}
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Feedback history — previous revisions */}
            {feedbackHistory.map((item, idx) => (
              <div key={idx} className="mt-6">
                <div className="mb-4">
                  <div className="mb-2 flex items-center gap-2">
                    <div
                      className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white"
                      style={{ backgroundColor: "#16a34a" }}
                    >
                      You
                    </div>
                    <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                      Your Feedback
                    </span>
                  </div>
                  <div
                    className="ml-9 rounded-xl p-4"
                    style={{ backgroundColor: "#f0fdf4", border: "1px solid #bbf7d0" }}
                  >
                    <p className="text-[13px] leading-relaxed" style={{ color: "#166534" }}>
                      {item.feedback}
                    </p>
                  </div>
                </div>
                <div>
                  <div className="mb-2 flex items-center gap-2">
                    <div
                      className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                      style={{ backgroundColor: "#eef2ff", color: "#3366FF" }}
                    >
                      AI
                    </div>
                    <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                      Revised Draft
                    </span>
                    <span
                      className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                      style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
                    >
                      v{idx + 2}
                    </span>
                  </div>
                  <div
                    className="ml-9 rounded-xl p-4"
                    style={{ backgroundColor: "#f0f4ff", border: "1px solid #dde4f8" }}
                  >
                    <p className="text-[13px] leading-relaxed whitespace-pre-wrap" style={{ color: "#2d3a6e" }}>
                      {item.revisedDraft}
                    </p>
                  </div>
                </div>
              </div>
            ))}

            {/* Sent timestamp */}
            {selectedReply.sent_at && (
              <div className="mt-6 flex items-center gap-2">
                <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
                <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "#a5abbe" }}>
                  Sent {new Date(selectedReply.sent_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                    timeZone: "America/New_York",
                  })}
                </span>
                <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
              </div>
            )}
          </div>

          {/* Error message */}
          {actionError && (
            <div className="px-6 py-2" style={{ backgroundColor: "#fef2f2", borderTop: "1px solid #fecaca" }}>
              <p className="text-[12px] font-medium" style={{ color: "#ef4444" }}>{actionError}</p>
            </div>
          )}

          {/* Needs Josh's Help bar */}
          {selectedReply.status === "needs_josh" && (
            <div
              className="flex items-center gap-3 px-6 py-3"
              style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#fff7ed" }}
            >
              <svg className="h-4 w-4" fill="none" stroke="#ea580c" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <span className="text-[12px] font-semibold" style={{ color: "#ea580c" }}>
                Needs Josh's Help
              </span>
              <span className="text-[11px]" style={{ color: "#a5abbe" }}>
                The AI could not confidently respond. Josh needs to reply manually.
              </span>
            </div>
          )}

          {/* Managed by Human bar */}
          {selectedReply.status === "human_managed" && (
            <div
              className="flex items-center gap-3 px-6 py-3"
              style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#eef2ff" }}
            >
              <svg className="h-4 w-4" fill="none" stroke="#6366f1" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span className="text-[12px] font-semibold" style={{ color: "#6366f1" }}>
                Managed by Human
              </span>
              <span className="text-[11px]" style={{ color: "#a5abbe" }}>
                A team member already replied to this conversation
              </span>
            </div>
          )}

          {/* Approve / Reject buttons */}
          {selectedReply.draft_response &&
            selectedReply.status !== "sent" &&
            selectedReply.status !== "rejected" &&
            selectedReply.status !== "auto_handled" &&
            selectedReply.status !== "human_managed" &&
            selectedReply.status !== "needs_josh" && (
            <div
              className="flex items-center gap-2 px-6 py-3"
              style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#fafbfd" }}
            >
              <button
                onClick={handleApprove}
                disabled={approveLoading || rejectLoading}
                className="flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-[12px] font-semibold transition-opacity disabled:opacity-50"
                style={{ backgroundColor: "#eef2ff", color: "#3366FF", border: "1px solid #dde4f8", minWidth: "130px" }}
              >
                {approveLoading ? (
                  <div
                    className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#3366FF]"
                    style={{ borderTopColor: "transparent" }}
                  />
                ) : (
                  <>
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Approve & Send
                  </>
                )}
              </button>
              <button
                onClick={handleReject}
                disabled={approveLoading || rejectLoading}
                className="flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-[12px] font-semibold transition-opacity disabled:opacity-50"
                style={{ backgroundColor: "#fef2f2", color: "#ef4444", border: "1px solid #fecaca", minWidth: "130px" }}
              >
                {rejectLoading ? (
                  <div
                    className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#ef4444]"
                    style={{ borderTopColor: "transparent" }}
                  />
                ) : (
                  <>
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    Reject
                  </>
                )}
              </button>
              <span className="ml-auto text-[11px]" style={{ color: "#a5abbe" }}>
                Sends reply via Instantly.ai & notifies Slack
              </span>
            </div>
          )}

          {/* Feedback input */}
          {selectedReply.draft_response && selectedReply.status !== "sent" && selectedReply.status !== "rejected" && selectedReply.status !== "human_managed" && selectedReply.status !== "needs_josh" && (
            <div
              className="flex items-center gap-3 px-6 py-3"
              style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#fafbfd" }}
            >
              <input
                type="text"
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !feedbackLoading) handleFeedbackSubmit();
                }}
                placeholder="Give feedback on this draft... (e.g. make it shorter, add pricing)"
                disabled={feedbackLoading}
                className="flex-1 rounded-lg px-3 py-2 text-[13px] outline-none disabled:opacity-50"
                style={{ border: "1px solid #e2e6ee", color: "#1a1a2e" }}
              />
              <button
                onClick={handleFeedbackSubmit}
                disabled={feedbackLoading || !feedbackText.trim()}
                className="shrink-0 rounded-lg px-4 py-2 text-[12px] font-semibold text-white transition-opacity disabled:opacity-40"
                style={{ backgroundColor: "#3366FF" }}
              >
                {feedbackLoading ? (
                  <div
                    className="h-4 w-4 animate-spin rounded-full border-2 border-white"
                    style={{ borderTopColor: "transparent" }}
                  />
                ) : (
                  "Revise"
                )}
              </button>
            </div>
          )}

          {/* Bottom info bar — shown when sent or no draft */}
          {(selectedReply.status === "sent" || (!selectedReply.draft_response && selectedReply.status !== "human_managed")) && (
            <div
              className="flex items-center gap-4 px-6 py-3"
              style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#fafbfd" }}
            >
              <span className="text-[11px]" style={{ color: "#a5abbe" }}>
                Reply managed via Slack approval workflow
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
