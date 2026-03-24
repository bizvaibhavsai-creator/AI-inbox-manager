"use client";

import { useEffect, useState } from "react";
import KPICard from "@/components/KPICard";
import CategoryPieChart from "@/components/CategoryPieChart";
import TimelineChart from "@/components/TimelineChart";
import PeriodFilter from "@/components/PeriodFilter";
import {
  getStatsOverview,
  getTimeline,
  getResponseTimes,
  getFollowUpStats,
  type StatsOverview,
  type TimelineEntry,
  type ResponseTimes,
  type FollowUpStats,
} from "@/lib/api";

export default function OverviewPage() {
  const [period, setPeriod] = useState("all");
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [responseTimes, setResponseTimes] = useState<ResponseTimes | null>(null);
  const [followUps, setFollowUps] = useState<FollowUpStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [ov, tl, rt, fu] = await Promise.all([
          getStatsOverview(period),
          getTimeline(30),
          getResponseTimes(),
          getFollowUpStats(),
        ]);
        setOverview(ov);
        setTimeline(tl.timeline);
        setResponseTimes(rt);
        setFollowUps(fu);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [period]);

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="rounded-2xl bg-white p-8 text-center" style={{ border: "1px solid #e2e6ee" }}>
          <p className="text-[14px] font-medium" style={{ color: "#ef4444" }}>{error}</p>
          <p className="mt-2 text-[12px]" style={{ color: "#a5abbe" }}>
            Make sure the backend is running on {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8888"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight" style={{ color: "#1a1a2e" }}>
            Overview
          </h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "#8a91a5" }}>
            Real-time inbox management analytics
          </p>
        </div>
        <PeriodFilter value={period} onChange={setPeriod} />
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-[#e2e6ee]" style={{ borderTopColor: "#3366FF" }} />
        </div>
      ) : overview ? (
        <>
          {/* KPI Cards */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard title="Total Responses" value={overview.total} color="indigo" />
            <KPICard title="Interested" value={overview.interested} color="green" />
            <KPICard title="Not Interested" value={overview.not_interested} color="red" />
            <KPICard title="Out of Office" value={overview.ooo} color="yellow" />
          </div>

          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard title="Unsubscribe" value={overview.unsubscribe} color="gray" />
            <KPICard title="Info Request" value={overview.info_request} color="purple" />
            <KPICard
              title="Pending Approval"
              value={overview.pending_approval}
              color="orange"
              subtitle="Awaiting Slack response"
            />
            <KPICard
              title="Sent"
              value={overview.sent}
              color="green"
              subtitle={
                overview.approval_rate
                  ? `${overview.approval_rate.toFixed(0)}% approval rate`
                  : undefined
              }
            />
          </div>

          {/* Response time cards */}
          {responseTimes && (
            <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-3">
              <KPICard
                title="Avg Approval Time"
                value={
                  responseTimes.avg_approval_time_minutes
                    ? `${responseTimes.avg_approval_time_minutes.toFixed(0)} min`
                    : "N/A"
                }
                color="purple"
              />
              <KPICard
                title="Avg Response Time"
                value={
                  responseTimes.avg_send_time_minutes
                    ? `${responseTimes.avg_send_time_minutes.toFixed(0)} min`
                    : "N/A"
                }
                color="blue"
              />
              <KPICard
                title="Total Sent"
                value={responseTimes.total_sent}
                color="green"
              />
            </div>
          )}

          {/* Charts */}
          <div className="mb-8 grid gap-5 lg:grid-cols-2">
            <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
              <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
                Category Breakdown
              </h2>
              <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
                Distribution of reply types
              </p>
              <CategoryPieChart data={overview} />
            </div>
            <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
              <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
                Daily Volume
              </h2>
              <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
                Last 30 days
              </p>
              <TimelineChart data={timeline} />
            </div>
          </div>

          {/* Follow-up stats */}
          {followUps && followUps.total > 0 && (
            <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
              <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
                Follow-Up Stats
              </h2>
              <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
                Automated follow-up sequences
              </p>
              <div className="grid grid-cols-3 gap-4">
                {Object.entries(followUps.by_sequence).map(([key, val]) => (
                  <div
                    key={key}
                    className="rounded-xl p-4 text-center"
                    style={{ backgroundColor: "#f8f9fc" }}
                  >
                    <p className="text-[11px] font-medium" style={{ color: "#8a91a5" }}>
                      {key.replace("_", " ").replace("followup", "Follow-up #")}
                    </p>
                    <p className="mt-1 text-[24px] font-semibold" style={{ color: "#1a1a2e" }}>
                      {val.sent}
                    </p>
                    <p className="text-[11px]" style={{ color: "#a5abbe" }}>
                      of {val.total} scheduled
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
