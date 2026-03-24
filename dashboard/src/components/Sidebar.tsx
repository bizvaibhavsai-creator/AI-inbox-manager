"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  {
    href: "/",
    label: "Overview",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    href: "/campaigns",
    label: "Campaigns",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    href: "/replies",
    label: "Replies",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 flex h-screen w-60 flex-col bg-white" style={{ borderRight: "1px solid #e2e6ee" }}>
      <div className="px-6 py-6">
        <h1 className="text-[15px] font-semibold tracking-tight" style={{ color: "#1a1a2e" }}>
          Inbox Manager
        </h1>
        <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide" style={{ color: "#9ca3b4" }}>
          AI-Powered
        </p>
      </div>

      <nav className="flex-1 px-3 pt-2">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
          Menu
        </p>
        {navItems.map((item) => {
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className="mb-0.5 flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all"
              style={
                isActive
                  ? { color: "#3366FF", backgroundColor: "#f0f4ff" }
                  : { color: "#5a6176" }
              }
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = "#f5f7fa";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
              }}
            >
              {item.icon}
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-5" style={{ borderTop: "1px solid #e2e6ee" }}>
        <p className="text-[11px] font-medium" style={{ color: "#b0b7c8" }}>v1.0 &middot; Powered by AI</p>
      </div>
    </aside>
  );
}
