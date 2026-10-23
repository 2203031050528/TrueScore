"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Spinner } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/format";

export interface NavItem {
  href: string;
  label: string;
}

export function Shell({ nav, children, wide }: { nav: NavItem[]; children: ReactNode; wide?: boolean }) {
  const { me, loading, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const simple = me?.profile?.simple_mode;

  return (
    <div className={cn("min-h-screen", simple && "text-lg")}>
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
        <div className={cn("mx-auto flex h-14 items-center gap-6 px-4", wide ? "max-w-7xl" : "max-w-6xl")}>
          <Link href={nav[0]?.href ?? "/"} className="flex items-center gap-2 font-semibold">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white">T</span>
            TrueScore
          </Link>
          <nav className="hidden flex-1 items-center gap-1 md:flex">
            {nav.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium",
                  pathname.startsWith(item.href) ? "bg-primary-soft text-primary" : "text-muted hover:bg-subtle hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-3 md:flex">
            {me && (
              <span className="text-sm text-muted">
                {me.full_name || me.username}
                {me.profile && ` · ${me.profile.section_label}`}
              </span>
            )}
            <button onClick={logout} className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:bg-subtle hover:text-foreground">
              Log out
            </button>
          </div>
          <button className="ml-auto rounded-lg px-3 py-1.5 text-sm md:hidden" onClick={() => setOpen(!open)} aria-expanded={open}>
            Menu
          </button>
        </div>
        {open && (
          <nav className="border-t border-border px-4 py-2 md:hidden">
            {nav.map((item) => (
              <Link key={item.href} href={item.href} onClick={() => setOpen(false)} className="block rounded-lg px-3 py-2 text-sm font-medium hover:bg-subtle">
                {item.label}
              </Link>
            ))}
            <button onClick={logout} className="block w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-danger hover:bg-subtle">
              Log out
            </button>
          </nav>
        )}
      </header>
      <main className={cn("mx-auto px-4 py-8", wide ? "max-w-7xl" : "max-w-6xl")}>{loading ? <Spinner /> : children}</main>
    </div>
  );
}
