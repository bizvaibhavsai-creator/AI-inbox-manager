"use client";

import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from "recharts";
import type { StatsOverview } from "@/lib/api";

const COLORS: Record<string, string> = {
  Interested: "#3366FF",
  "Not Interested": "#ef4444",
  OOO: "#f59e0b",
  Unsubscribe: "#94a3b8",
  "Info Request": "#6366f1",
  "Wrong Person": "#a78bfa",
  DNC: "#dc2626",
};

interface Props {
  data: StatsOverview;
}

export default function CategoryPieChart({ data }: Props) {
  const chartData = [
    { name: "Interested", value: data.interested },
    { name: "Not Interested", value: data.not_interested },
    { name: "OOO", value: data.ooo },
    { name: "Unsubscribe", value: data.unsubscribe },
    { name: "Info Request", value: data.info_request },
    { name: "Wrong Person", value: data.wrong_person },
    { name: "DNC", value: data.dnc },
  ].filter((d) => d.value > 0);

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={65}
          outerRadius={105}
          paddingAngle={4}
          dataKey="value"
          stroke="none"
          label={({ name, percent }) =>
            `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
        >
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={COLORS[entry.name] || "#94a3b8"} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            borderRadius: "12px",
            border: "1px solid #e2e6ee",
            boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
            fontSize: "12px",
            fontFamily: "Inter",
          }}
        />
        <Legend
          wrapperStyle={{ fontSize: "12px", fontFamily: "Inter" }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
