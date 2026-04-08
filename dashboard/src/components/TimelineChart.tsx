"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { TimelineEntry } from "@/lib/api";

interface Props {
  data: TimelineEntry[];
}

export default function TimelineChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No data yet
      </div>
    );
  }

  const formatted = data.map((d) => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "America/New_York",
    }),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={formatted}>
        <defs>
          <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3366FF" stopOpacity={0.15} />
            <stop offset="100%" stopColor="#3366FF" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="greenGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22c55e" stopOpacity={0.1} />
            <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#eef1f6" vertical={false} />
        <XAxis
          dataKey="date"
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
        <Area
          type="monotone"
          dataKey="total"
          stroke="#3366FF"
          strokeWidth={2}
          fill="url(#blueGrad)"
          name="Total"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="interested"
          stroke="#22c55e"
          strokeWidth={1.5}
          fill="url(#greenGrad)"
          name="Interested"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
