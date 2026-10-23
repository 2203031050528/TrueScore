"use client";

import { useState } from "react";

export interface BarItem {
  key: string | number;
  label: string;
  value: number; // 0–100
  detail?: string;
}

/** Horizontal single-series bars (magnitude 0–100%): thin bars, rounded data-end, value at the tip, hover detail. */
export function BarList({ items, ariaLabel }: { items: BarItem[]; ariaLabel: string }) {
  const [hover, setHover] = useState<string | number | null>(null);
  return (
    <ul className="space-y-3" aria-label={ariaLabel}>
      {items.map((item) => {
        const pct = Math.max(0, Math.min(100, item.value));
        return (
          <li
            key={item.key}
            className="relative"
            onPointerEnter={() => setHover(item.key)}
            onPointerLeave={() => setHover(null)}
          >
            <div className="mb-1 flex justify-between text-sm">
              <span className="truncate">{item.label}</span>
              <span className="ml-3 font-medium tabular-nums">{Math.round(pct)}%</span>
            </div>
            <div className="h-2.5 w-full rounded-r bg-subtle">
              <div className="h-full rounded-r-[4px] bg-primary transition-[width]" style={{ width: `${pct}%` }} />
            </div>
            {hover === item.key && item.detail && (
              <div className="pointer-events-none absolute right-0 top-full z-10 mt-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs shadow-md">
                {item.detail}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
