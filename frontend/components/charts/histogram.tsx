"use client";

import { useState } from "react";

/** Single-series column chart for a score distribution: thin columns, rounded caps, value on the cap, hover detail. */
export function Histogram({ buckets, unit = "students" }: { buckets: { range: string; count: number }[]; unit?: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...buckets.map((b) => b.count));
  return (
    <div>
      <div className="flex h-44 items-end gap-1 border-b border-border" role="img" aria-label="Score distribution">
        {buckets.map((b, i) => (
          <div
            key={b.range}
            className="relative flex h-full flex-1 flex-col items-center justify-end"
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
          >
            {b.count > 0 && <span className="mb-1 text-xs font-medium tabular-nums">{b.count}</span>}
            <div
              className="w-full max-w-6 rounded-t-[4px] bg-primary transition-opacity"
              style={{ height: `${(b.count / max) * 85}%`, opacity: hover === null || hover === i ? 1 : 0.55 }}
            />
            {hover === i && (
              <div className="pointer-events-none absolute -top-2 z-10 -translate-y-full whitespace-nowrap rounded-md border border-border bg-surface px-2 py-1 text-xs shadow-md">
                {b.range}: <b>{b.count}</b> {unit}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-1 text-[10px] text-muted">
        {buckets.map((b) => (
          <span key={b.range} className="flex-1 text-center">{b.range.split("-")[0]}</span>
        ))}
      </div>
      <p className="mt-1 text-center text-xs text-muted">Score (%)</p>
    </div>
  );
}
