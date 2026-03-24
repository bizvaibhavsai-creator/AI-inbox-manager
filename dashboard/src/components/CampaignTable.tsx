"use client";

import type { CampaignStats } from "@/lib/api";

interface Props {
  campaigns: CampaignStats[];
}

export default function CampaignTable({ campaigns }: Props) {
  if (campaigns.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No campaign data yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr style={{ borderBottom: "1px solid #e2e6ee" }}>
            <th className="pb-3 pr-4 text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Campaign</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Total</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Interested</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Not Interested</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>OOO</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Unsub</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Info Req</th>
            <th className="pb-3 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Rate</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <tr
              key={c.campaign_id}
              className="transition-colors hover:bg-[#f8f9fc]"
              style={{ borderBottom: "1px solid #f0f2f7" }}
            >
              <td className="py-3.5 pr-4 font-medium" style={{ color: "#1a1a2e" }}>
                {c.campaign_name || c.campaign_id}
              </td>
              <td className="py-3.5 pr-4 text-right font-medium" style={{ color: "#5a6176" }}>{c.total}</td>
              <td className="py-3.5 pr-4 text-right font-semibold" style={{ color: "#3366FF" }}>
                {c.interested}
              </td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#ef4444" }}>
                {c.not_interested}
              </td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#f59e0b" }}>{c.ooo}</td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#94a3b8" }}>
                {c.unsubscribe}
              </td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#6366f1" }}>
                {c.info_request}
              </td>
              <td className="py-3.5 text-right">
                <span
                  className="inline-flex rounded-lg px-2.5 py-1 text-[11px] font-semibold"
                  style={
                    c.interest_rate >= 20
                      ? { backgroundColor: "#eef2ff", color: "#3366FF" }
                      : c.interest_rate >= 10
                      ? { backgroundColor: "#fffbeb", color: "#d97706" }
                      : { backgroundColor: "#fef2f2", color: "#ef4444" }
                  }
                >
                  {c.interest_rate}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
