import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "AI Inbox Manager",
  description: "Cold email response analytics dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased" style={{ color: "#1a1a2e" }}>
        <Sidebar />
        <main className="ml-60 min-h-screen p-8">{children}</main>
      </body>
    </html>
  );
}
