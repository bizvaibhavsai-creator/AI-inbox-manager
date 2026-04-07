"use client";

import { useEffect, useState } from "react";
import { getReplies, type ReplyItem } from "@/lib/api";

const categoryStyles: Record<string, { bg: string; color: string; label: string }> = {
  interested: { bg: "#eef2ff", color: "#3366FF", label: "Interested" },
  not_interested: { bg: "#fef2f2", color: "#ef4444", label: "Not Interested" },
  ooo: { bg: "#fffbeb", color: "#d97706", label: "OOO" },
  unsubscribe: { bg: "#f3f4f6", color: "#6b7280", label: "Unsubscribe" },
  info_request: { bg: "#eef2ff", color: "#6366f1", label: "Info Request" },
  wrong_person: { bg: "#f5f3ff", color: "#8b5cf6", label: "Wrong Person" },
  dnc: { bg: "#fef2f2", color: "#dc2626", label: "DNC" },
};

export default function SentPage() {
  const [replies, setReplies] = useState<ReplyItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getReplies(page, undefined, "sent");
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
  }, [page]);

  const selectedReply = replies.find((r) => r.id === selectedId);

  return (
    <div className="flex gap-0" style={{ height: "calc(100vh - 64px)" }}>
      {/* Left panel — sent list */}
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
              Sent Replies
            </h1>
            <p className="text-[11px]" style={{ color: "#a5abbe" }}>
              {total} sent
            </p>
          </div>
          <span
            className="rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
            style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
          >
            Sent
          </span>
        </div>

        {/* Sent rows */}
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
              No sent replies yet
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
                    backgroundColor: isActive ? "#f0fdf4" : "transparent",
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
                        {r.draft_response ? r.draft_response.slice(0, 60) + "..." : ""}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px]" style={{ color: "#a5abbe" }}>
                      {r.campaign_name}
                    </p>
                  </div>

                  {/* Time */}
                  <div className="shrink-0 text-right">
                    <p className="text-[11px] font-medium" style={{ color: "#a5abbe" }}>
                      {r.sent_at
                        ? new Date(r.sent_at).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            timeZone: "America/New_York",
                          })
                        : ""}
                    </p>
                    <span
                      className="mt-0.5 inline-block rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wider"
                      style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
                    >
                      Sent
                    </span>
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
                style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
              >
                Sent
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
            {/* Their original reply */}
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

            {/* Our sent response */}
            {selectedReply.draft_response && (
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <div
                    className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                    style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
                  >
                    <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                    Sent Response
                  </span>
                  <span
                    className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                    style={{ backgroundColor: "#f0fdf4", color: "#16a34a" }}
                  >
                    Sent
                  </span>
                </div>
                <div
                  className="ml-9 rounded-xl p-4"
                  style={{ backgroundColor: "#f0fdf4", border: "1px solid #bbf7d0" }}
                >
                  <p className="text-[13px] leading-relaxed" style={{ color: "#166534" }}>
                    {selectedReply.draft_response}
                  </p>
                </div>
              </div>
            )}

            {/* Sent timestamp */}
            {selectedReply.sent_at && (
              <div className="mt-6 flex items-center gap-2">
                <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
                <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "#16a34a" }}>
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

          {/* Bottom info bar */}
          <div
            className="flex items-center gap-4 px-6 py-3"
            style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#fafbfd" }}
          >
            <svg className="h-4 w-4" fill="none" stroke="#16a34a" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-[11px]" style={{ color: "#a5abbe" }}>
              Reply sent via Instantly.ai
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
