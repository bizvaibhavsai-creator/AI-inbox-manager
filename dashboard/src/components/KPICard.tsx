"use client";

interface KPICardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  color?: string;
}

const iconColors: Record<string, { dot: string; bg: string }> = {
  blue: { dot: "#3366FF", bg: "#eef2ff" },
  green: { dot: "#22c55e", bg: "#f0fdf4" },
  red: { dot: "#ef4444", bg: "#fef2f2" },
  yellow: { dot: "#f59e0b", bg: "#fffbeb" },
  purple: { dot: "#8b5cf6", bg: "#f5f3ff" },
  gray: { dot: "#6b7280", bg: "#f3f4f6" },
  orange: { dot: "#f97316", bg: "#fff7ed" },
  indigo: { dot: "#3366FF", bg: "#eef2ff" },
};

export default function KPICard({ title, value, subtitle, color = "blue" }: KPICardProps) {
  const scheme = iconColors[color] || iconColors.blue;

  return (
    <div
      className="rounded-2xl bg-white p-5"
      style={{ border: "1px solid #e2e6ee" }}
    >
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: scheme.dot }}
        />
        <p className="text-[12px] font-medium tracking-wide" style={{ color: "#8a91a5" }}>
          {title}
        </p>
      </div>
      <p className="mt-2 text-[28px] font-semibold leading-none tracking-tight" style={{ color: "#1a1a2e" }}>
        {value}
      </p>
      {subtitle && (
        <p className="mt-1.5 text-[11px] font-medium" style={{ color: "#a5abbe" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
