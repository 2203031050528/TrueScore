"use client";

import { useRef, useState } from "react";

import { fmtDate } from "@/lib/format";

export interface TrendPoint {
  label: string;
  date: string;
  value: number; // percentage 0–100
}

const W = 640;
const H = 220;
const PAD = { top: 16, right: 48, bottom: 28, left: 36 };
const TICKS = [0, 25, 50, 75, 100];

/** Single-series score trend: 2px line, ringed 8px markers, 10% wash, crosshair + tooltip on hover. */
export function ScoreTrend({ points, passLine }: { points: TrendPoint[]; passLine?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  if (points.length === 0) return null;

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? innerW / 2 : (i * innerW) / (points.length - 1));
  const y = (v: number) => PAD.top + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
  const area = `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const last = points[points.length - 1];

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const rect = svgRef.current!.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    points.forEach((_, i) => Math.abs(x(i) - px) < Math.abs(x(best) - px) && (best = i));
    setHover(best);
  }

  const h = hover === null ? null : points[hover];
  return (
    <div className="relative">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Score percentage per exam over time">
        {TICKS.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--color-border)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-[var(--color-muted)] text-[11px] tabular-nums">
              {t}%
            </text>
          </g>
        ))}
        {passLine !== undefined && (
          <line x1={PAD.left} x2={W - PAD.right} y1={y(passLine)} y2={y(passLine)} stroke="var(--color-muted)" strokeWidth={1} strokeOpacity={0.6} />
        )}
        <path d={area} fill="var(--color-primary)" fillOpacity={0.1} />
        <path d={line} fill="none" stroke="var(--color-primary)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {h && hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={y(0)} stroke="var(--color-muted)" strokeWidth={1} />}
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={hover === i ? 6 : 4} fill="var(--color-primary)" stroke="var(--color-surface)" strokeWidth={2} />
        ))}
        <text x={x(points.length - 1) + 10} y={y(last.value)} dy="0.32em" className="fill-[var(--color-foreground)] text-[12px] font-semibold tabular-nums">
          {Math.round(last.value)}%
        </text>
        <rect
          x={PAD.left - 12}
          y={0}
          width={innerW + 24}
          height={H}
          fill="transparent"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        />
      </svg>
      {h && hover !== null && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-md"
          style={{ left: `${(x(hover) / W) * 100}%`, top: 0 }}
        >
          <p className="font-medium">{h.label}</p>
          <p className="text-muted">{fmtDate(h.date)}</p>
          <p className="mt-1 font-semibold tabular-nums">{h.value.toFixed(1)}%</p>
        </div>
      )}
    </div>
  );
}
