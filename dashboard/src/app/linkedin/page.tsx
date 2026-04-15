"use client";

import { useEffect, useState } from "react";
import {
  getLinkedInAnalyticsDashboard,
  syncLinkedInCampaigns,
  syncLinkedInConversations,
  type LinkedInAnalyticsDashboard,
} from "@/lib/api";

const categoryLabels: Record<string, string> = {
  interested: "Interested",
  not_interested: "Not Interested",
  info_request: "Info Request",
  referral: "Referral",
  wrong_person: "Wrong Person",
  out_of_office: "Out of Office",
  already_client: "Already Client",
  outgoing: "Outgoing",
};

const categoryColors: Record<string, string> = {
  interested: "#3366FF",
  not_interested: "#ef4444",
  info_request: "#6366f1",
  referral: "#f59e0b",
  wrong_person: "#8b5cf6",
  out_of_office: "#d97706",
  already_client: "#10b981",
  outgoing: "#9ca3af",
};

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div
      className="rounded-2xl bg-white p-5"
      style={{ border: "1px solid #e2e6ee" }}
    >
      <p className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#a5abbe" }}>
        {label}
      </p>
      <p className="mt-2 text-[26px] font-bold tracking-tight" style={{ color: "#1a1a2e" }}>
        {value}
      </p>
      {sub && (
        <p className="mt-0.5 text-[11px]" style={{ color: "#a5abbe" }}>
          {sub}
        </p>
      )}
    </div>
  );
}

export default function LinkedInAnalyticsPage() {
  const [data, setData] = useState<LinkedInAnalyticsDashboard | null>(null);
  const [period, setPeriod] = useState("month");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");

  useEffect(() => {
    setLoading(true);
    getLinkedInAnalyticsDashboard(period)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [period]);

  async function handleSync() {
    setSyncing(true);
    setSyncMsg("");
    try {
      const cr = await syncLinkedInCampaigns();
      const cs = await syncLinkedInConversations();
      setSyncMsg(`Synced: ${cr.created} new campaigns, ${cs.count} new conversations`);
      const fresh = await getLinkedInAnalyticsDashboard(period);
      setData(fresh);
    } catch (e: unknown) {
      setSyncMsg(`Sync error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSyncing(false);
    }
  }

  const hs = data?.heyreach_stats;

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-[20px] font-bold" style={{ color: "#1a1a2e" }}>
            LinkedIn Analytics
          </h1>
          <p className="mt-0.5 text-[12px]" style={{ color: "#a5abbe" }}>
            HeyReach campaigns and inbox performance
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="rounded-lg px-3 py-2 text-[12px] font-medium outline-none"
            style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
          >
            <option value="today">Today</option>
            <option value="week">Last 7 Days</option>
            <option value="month">Last 30 Days</option>
            <option value="all">All Time</option>
          </select>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="rounded-xl px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
            style={{ backgroundColor: "#0A66C2" }}
          >
            {syncing ? "Syncing..." : "Sync HeyReach"}
          </button>
        </div>
      </div>

      {syncMsg && (
        <div
          className="mb-4 rounded-xl px-4 py-3 text-[12px]"
          style={{ backgroundColor: "#f0f4ff", color: "#3366FF", border: "1px solid #c7d4ff" }}
        >
          {syncMsg}
        </div>
      )}

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div
            className="h-8 w-8 animate-spin rounded-full border-[3px] border-[#e2e6ee]"
            style={{ borderTopColor: "#0A66C2" }}
          />
        </div>
      ) : !data ? (
        <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
          No data available. Click Sync HeyReach to load campaigns.
        </div>
      ) : (
        <>
          {/* HeyReach live KPI stats */}
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
            HeyReach Live Stats ({data.heyreach_stats_period.start_date} to {data.heyreach_stats_period.end_date})
          </p>
          {data.heyreach_stats_error && (
            <div className="mb-3 rounded-xl px-4 py-2 text-[11px]" style={{ backgroundColor: "#fef2f2", color: "#ef4444" }}>
              HeyReach API error: {data.heyreach_stats_error}
            </div>
          )}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatCard
              label="Connections Sent"
              value={hs?.connections_sent.toLocaleString() ?? 0}
            />
            <StatCard
              label="Accepted"
              value={hs?.connections_accepted.toLocaleString() ?? 0}
              sub={`${((hs?.acceptance_rate ?? 0) * 100).toFixed(1)}% acceptance`}
            />
            <StatCard
              label="Messages Replied"
              value={hs?.messages_replied.toLocaleString() ?? 0}
              sub={`${((hs?.reply_rate ?? 0) * 100).toFixed(1)}% reply rate`}
            />
            <StatCard
              label="InMails Replied"
              value={hs?.inmails_replied.toLocaleString() ?? 0}
              sub={`${((hs?.inmail_reply_rate ?? 0) * 100).toFixed(1)}% reply rate`}
            />
            <StatCard
              label="Profile Views"
              value={hs?.profile_views.toLocaleString() ?? 0}
            />
          </div>

          {/* Inbox stats */}
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
            Inbox Performance
          </p>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Total Replies" value={data.total_conversations} />
            <StatCard
              label="Interest Rate"
              value={`${(data.interest_rate * 100).toFixed(1)}%`}
              sub={`${data.by_category.interested} interested`}
            />
            <StatCard
              label="Avg Response"
              value={`${data.avg_response_hours}h`}
            />
            <StatCard
              label="Sent"
              value={data.by_status.sent ?? 0}
              sub={`${data.by_status.pending_approval ?? 0} pending`}
            />
          </div>

          {/* Category breakdown + Campaigns */}
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Category breakdown */}
            <div className="rounded-2xl bg-white p-5" style={{ border: "1px solid #e2e6ee" }}>
              <p className="mb-4 text-[13px] font-semibold" style={{ color: "#1a1a2e" }}>
                Replies by Category
              </p>
              {Object.entries(data.by_category).map(([cat, count]) => {
                const pct = data.total_conversations ? Math.round((count / data.total_conversations) * 100) : 0;
                const color = categoryColors[cat] || "#6b7280";
                return (
                  <div key={cat} className="mb-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-[12px] font-medium" style={{ color: "#5a6176" }}>
                        {categoryLabels[cat] || cat}
                      </span>
                      <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                        {count} <span className="font-normal" style={{ color: "#a5abbe" }}>({pct}%)</span>
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ backgroundColor: "#f0f2f7" }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${pct}%`, backgroundColor: color }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Daily volumes — simplified bar chart */}
            <div className="rounded-2xl bg-white p-5" style={{ border: "1px solid #e2e6ee" }}>
              <p className="mb-4 text-[13px] font-semibold" style={{ color: "#1a1a2e" }}>
                Daily Reply Volume (Last 30 Days)
              </p>
              <div className="flex h-32 items-end gap-[2px]">
                {data.daily_volumes.map((d) => {
                  const max = Math.max(...data.daily_volumes.map((x) => x.count), 1);
                  const pct = Math.round((d.count / max) * 100);
                  return (
                    <div
                      key={d.date}
                      title={`${d.date}: ${d.count}`}
                      className="flex-1 rounded-t-sm transition-all"
                      style={{
                        height: `${Math.max(pct, d.count > 0 ? 4 : 0)}%`,
                        backgroundColor: d.count > 0 ? "#0A66C2" : "#e2e6ee",
                        opacity: d.count > 0 ? 0.8 : 1,
                      }}
                    />
                  );
                })}
              </div>
              <div className="mt-2 flex justify-between text-[9px]" style={{ color: "#b0b7c8" }}>
                <span>{data.daily_volumes[0]?.date.slice(5)}</span>
                <span>{data.daily_volumes[data.daily_volumes.length - 1]?.date.slice(5)}</span>
              </div>
            </div>
          </div>

          {/* Campaign table */}
          <div className="rounded-2xl bg-white" style={{ border: "1px solid #e2e6ee" }}>
            <div className="px-5 py-4" style={{ borderBottom: "1px solid #e2e6ee" }}>
              <p className="text-[13px] font-semibold" style={{ color: "#1a1a2e" }}>
                Campaigns ({data.campaigns.length})
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr style={{ borderBottom: "1px solid #f0f2f7" }}>
                    <th className="px-5 py-3 text-left font-semibold" style={{ color: "#a5abbe" }}>Campaign</th>
                    <th className="px-3 py-3 text-center font-semibold" style={{ color: "#a5abbe" }}>Status</th>
                    <th className="px-3 py-3 text-center font-semibold" style={{ color: "#a5abbe" }}>Replies</th>
                    <th className="px-3 py-3 text-center font-semibold" style={{ color: "#a5abbe" }}>Interested</th>
                    <th className="px-3 py-3 text-center font-semibold" style={{ color: "#a5abbe" }}>Interest Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.campaigns.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-8 text-center" style={{ color: "#a5abbe" }}>
                        No campaigns synced yet. Click Sync HeyReach.
                      </td>
                    </tr>
                  ) : (
                    data.campaigns.map((camp) => (
                      <tr
                        key={camp.id}
                        style={{ borderBottom: "1px solid #f0f2f7" }}
                      >
                        <td className="px-5 py-3 font-medium" style={{ color: "#1a1a2e", maxWidth: "220px" }}>
                          <span className="block truncate">{camp.name}</span>
                        </td>
                        <td className="px-3 py-3 text-center">
                          <span
                            className="rounded-md px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                            style={{
                              backgroundColor: camp.status === "active" ? "#f0fdf4" : "#f3f4f6",
                              color: camp.status === "active" ? "#16a34a" : "#6b7280",
                            }}
                          >
                            {camp.status}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-center font-semibold" style={{ color: "#1a1a2e" }}>
                          {camp.total_conversations}
                        </td>
                        <td className="px-3 py-3 text-center" style={{ color: "#3366FF" }}>
                          {camp.by_category.interested}
                        </td>
                        <td className="px-3 py-3 text-center font-semibold" style={{ color: camp.interest_rate > 0.1 ? "#16a34a" : "#1a1a2e" }}>
                          {(camp.interest_rate * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
