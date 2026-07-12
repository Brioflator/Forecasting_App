import type { Metadata } from "next";
import Link from "next/link";
import { Labrada } from "next/font/google";
import { GeistMono } from "geist/font/mono";
import { Plant, Plus, List } from "@phosphor-icons/react/dist/ssr";

import AppSidebar, { NavList } from "@/components/AppSidebar";
import NotificationBell from "@/components/NotificationBell";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { getSession } from "@/lib/auth";
import "./globals.css";

// Labrada (Omnibus-Type) is the app-wide face; Geist Mono stays for numerals
// and code so tabular figures keep lining up.
const labrada = Labrada({
  subsets: ["latin"],
  variable: "--font-labrada",
});

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
    <html lang="en" className={`${labrada.variable} ${GeistMono.variable}`}>
      <body className="font-sans">
        <TooltipProvider delayDuration={300}>
          <div className="flex min-h-screen">
            <AppSidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <header className="flex items-center justify-between gap-4 border-b border-sage/20 bg-surface/75 px-6 py-4 backdrop-blur-md lg:px-10">
                <div className="flex items-center gap-3">
                  <Sheet>
                    <SheetTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="lg:hidden"
                        aria-label="Open navigation"
                      >
                        <List size={20} weight="regular" />
                      </Button>
                    </SheetTrigger>
                    <SheetContent side="left" className="w-64">
                      <SheetHeader>
                        <SheetTitle className="flex items-center gap-2">
                          <Plant size={22} weight="regular" className="text-hunter" />
                          Forecast
                        </SheetTitle>
                      </SheetHeader>
                      <div className="mt-4">
                        <NavList />
                      </div>
                    </SheetContent>
                  </Sheet>
                  <span className="rounded-full bg-sage/20 px-3 py-1 text-xs font-medium text-pine">
                    {session.orgName}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <Button asChild size="sm">
                    <Link href="/connectors/new">
                      <Plus size={16} weight="regular" />
                      New connector
                    </Link>
                  </Button>
                  <NotificationBell />
                </div>
              </header>
              <main className="max-w-none flex-1 px-6 py-8 lg:px-10">{children}</main>
            </div>
          </div>
          <Toaster />
        </TooltipProvider>
      </body>
    </html>
  );
}
