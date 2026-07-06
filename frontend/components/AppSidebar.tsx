"use client";

// Left navigation shell (doc 4 §7b). Client component so the active item can
// be derived from the current pathname. Desktop (lg+) renders as a fixed
// sidebar; the same nav list is reused inside the mobile Sheet from
// app/layout.tsx.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Plant, SquaresFour, Plugs, Database, Robot, Bell } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: SquaresFour },
  { href: "/connectors", label: "Connectors", icon: Plugs },
  { href: "/metrics", label: "Datasets", icon: Database },
  { href: "/agents", label: "Agents", icon: Robot },
  { href: "/notifications", label: "Notifications", icon: Bell },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-hunter/10 text-hunter"
                : "text-ink/70 hover:bg-muted/60 hover:text-ink"
            )}
          >
            <Icon size={20} weight="regular" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export default function AppSidebar() {
  return (
    <aside className="hidden lg:flex lg:w-64 lg:flex-col lg:border-r lg:border-sage/20 lg:bg-surface">
      <div className="flex items-center gap-2 px-6 py-6">
        <Plant size={24} weight="regular" className="text-hunter" />
        <span className="text-lg font-semibold text-pine">Forecast</span>
      </div>
      <div className="flex-1 px-3">
        <NavList />
      </div>
    </aside>
  );
}
