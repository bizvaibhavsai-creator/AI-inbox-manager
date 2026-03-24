"use client";

interface Props {
  value: string;
  onChange: (period: string) => void;
}

const periods = [
  { label: "Today", value: "today" },
  { label: "This Week", value: "week" },
  { label: "This Month", value: "month" },
  { label: "All Time", value: "all" },
];

export default function PeriodFilter({ value, onChange }: Props) {
  return (
    <div
      className="flex gap-0.5 rounded-xl p-1"
      style={{ backgroundColor: "#eef1f6" }}
    >
      {periods.map((p) => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className="rounded-lg px-3.5 py-1.5 text-[12px] font-medium transition-all"
          style={
            value === p.value
              ? { backgroundColor: "#3366FF", color: "#ffffff" }
              : { color: "#8a91a5" }
          }
          onMouseEnter={(e) => {
            if (value !== p.value) e.currentTarget.style.color = "#1a1a2e";
          }}
          onMouseLeave={(e) => {
            if (value !== p.value) e.currentTarget.style.color = "#8a91a5";
          }}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
