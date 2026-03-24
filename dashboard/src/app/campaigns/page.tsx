"use client";

import { useEffect, useState } from "react";
import CampaignTable from "@/components/CampaignTable";
import CampaignBarChart from "@/components/CampaignBarChart";
import PeriodFilter from "@/components/PeriodFilter";
import KPICard from "@/components/KPICard";
import { getCampaignStats, type CampaignStats } from "@/lib/api";

export default function CampaignsPage() {
  const [period, setPeriod] = useState("all");
  const [campaigns, setCampaigns] = useState<CampaignStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getCampaignStats(period);
        setCampaigns(data.campaigns);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [period]);

  const bestCampaign = campaigns.reduce(
    (best, c) => (c.interest_rate > (best?.interest_rate ?? 0) ? c : best),
    null as CampaignStats | null
  );
  const worstCampaign = campaigns.reduce(
    (worst, c) =>
      c.total >= 5 && c.interest_rate < (worst?.interest_rate ?? 100)
        ? c
        : worst,
    null as CampaignStats | null
  );
  const highUnsubCampaign = campaigns.find(
    (c) => c.total >= 10 && c.unsubscribe / c.total > 0.05
  );

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight" style={{ color: "#1a1a2e" }}>
            Campaigns
          </h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "#8a91a5" }}>
            Per-campaign response breakdown
          </p>
        </div>
        <PeriodFilter value={period} onChange={setPeriod} />
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-[#e2e6ee]" style={{ borderTopColor: "#3366FF" }} />
        </div>
      ) : error ? (
        <div className="rounded-2xl bg-white p-8 text-center" style={{ border: "1px solid #e2e6ee", color: "#ef4444" }}>
          {error}
        </div>
      ) : (
        <>
          {/* Quick KPIs */}
          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard
              title="Total Campaigns"
              value={campaigns.length}
              color="indigo"
            />
            {bestCampaign && (
              <KPICard
                title="Best Campaign"
                value={`${bestCampaign.interest_rate}%`}
                subtitle={bestCampaign.campaign_name}
                color="green"
              />
            )}
            {worstCampaign && (
              <KPICard
                title="Lowest Interest Rate"
                value={`${worstCampaign.interest_rate}%`}
                subtitle={worstCampaign.campaign_name}
                color="red"
              />
            )}
            {highUnsubCampaign && (
              <KPICard
                title="High Unsubscribe Alert"
                value={`${((highUnsubCampaign.unsubscribe / highUnsubCampaign.total) * 100).toFixed(1)}%`}
                subtitle={highUnsubCampaign.campaign_name}
                color="orange"
              />
            )}
          </div>

          {/* Stacked bar chart */}
          <div className="mb-6 rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
            <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
              Category Distribution by Campaign
            </h2>
            <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
              Stacked breakdown per campaign
            </p>
            <CampaignBarChart campaigns={campaigns} />
          </div>

          {/* Campaign table */}
          <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
            <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
              All Campaigns
            </h2>
            <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
              Sorted by total replies
            </p>
            <CampaignTable campaigns={campaigns} />
          </div>
        </>
      )}
    </div>
  );
}
