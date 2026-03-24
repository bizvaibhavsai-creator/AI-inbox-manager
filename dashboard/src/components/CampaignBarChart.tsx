"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { CampaignStats } from "@/lib/api";

interface Props {
  campaigns: CampaignStats[];
}

export default function CampaignBarChart({ campaigns }: Props) {
  if (campaigns.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No data yet
      </div>
    );
  }

  const chartData = campaigns.slice(0, 10).map((c) => ({
    name: (c.campaign_name || c.campaign_id).slice(0, 20),
    Interested: c.interested,
    "Not Interested": c.not_interested,
    OOO: c.ooo,
    Unsubscribe: c.unsubscribe,
    "Info Request": c.info_request,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} barCategoryGap="20%">
        <CartesianGrid stroke="#eef1f6" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11, fill: "#8a91a5", fontFamily: "Inter" }}
          axisLine={{ stroke: "#e2e6ee" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#8a91a5", fontFamily: "Inter" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            borderRadius: "12px",
            border: "1px solid #e2e6ee",
            boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
            fontSize: "12px",
            fontFamily: "Inter",
          }}
        />
        <Legend wrapperStyle={{ fontSize: "12px", fontFamily: "Inter" }} />
        <Bar dataKey="Interested" stackId="a" fill="#3366FF" radius={[0, 0, 0, 0]} />
        <Bar dataKey="Not Interested" stackId="a" fill="#ef4444" />
        <Bar dataKey="OOO" stackId="a" fill="#f59e0b" />
        <Bar dataKey="Unsubscribe" stackId="a" fill="#94a3b8" />
        <Bar dataKey="Info Request" stackId="a" fill="#6366f1" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
