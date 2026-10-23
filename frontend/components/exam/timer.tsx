"use client";

import { useEffect, useState } from "react";

import { cn, fmtDuration } from "@/lib/format";

/** Countdown driven by the server's deadline and clock offset — changing the device clock does nothing. */
export function Timer({ deadline, offsetMs, onExpire, large }: { deadline: string; offsetMs: number; onExpire: () => void; large?: boolean }) {
  const remaining = () => Math.max(0, (new Date(deadline).getTime() - (Date.now() + offsetMs)) / 1000);
  const [left, setLeft] = useState(remaining);

  useEffect(() => {
    let fired = false;
    const tick = () => {
      const r = remaining();
      setLeft(r);
      if (r <= 0 && !fired) {
        fired = true;
        onExpire();
      }
    };
    tick();
    const t = setInterval(tick, 500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadline, offsetMs]);

  const warn = left <= 300;
  return (
    <div
      className={cn(
        "rounded-lg px-3 py-1.5 font-mono font-semibold tabular-nums",
        large ? "text-2xl" : "text-lg",
        left <= 60 ? "bg-danger text-white" : warn ? "bg-warning-soft text-warning" : "bg-subtle",
      )}
      role="timer"
      aria-live={warn ? "polite" : "off"}
    >
      {fmtDuration(left)}
    </div>
  );
}
