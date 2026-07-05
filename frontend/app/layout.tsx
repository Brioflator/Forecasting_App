import type { Metadata } from "next";
import Link from "next/link";
import { getSession } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forecast Platform",
  description: "Configure metrics, collect data on a schedule, get forecasts.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = getSession();
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
              <Link href="/" className="text-lg font-semibold">
                Forecast Platform
              </Link>
              <nav className="flex items-center gap-4 text-sm">
                <Link href="/connectors" className="text-slate-600 hover:text-slate-900">
                  Connectors
                </Link>
                <Link href="/metrics" className="text-slate-600 hover:text-slate-900">
                  Datasets
                </Link>
                <Link href="/agents" className="text-slate-600 hover:text-slate-900">
                  Agents
                </Link>
                <Link
                  href="/connectors/new"
                  className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                >
                  New connector
                </Link>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-500">
                  {session.orgName}
                </span>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
