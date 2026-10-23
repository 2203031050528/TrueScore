"use client";

import { cn } from "@/lib/format";
import type { PaperQuestion } from "@/lib/types";

export function isAnswered(q: PaperQuestion) {
  const a = q.answer;
  if (!a) return false;
  return Boolean(a.options?.length || (a.value ?? "").trim() || (a.text ?? "").trim());
}

export function Navigator({ questions, current, onGo, large }: { questions: PaperQuestion[]; current: number; onGo: (i: number) => void; large?: boolean }) {
  return (
    <div>
      <div className={cn("grid gap-2", large ? "grid-cols-4" : "grid-cols-5")}>
        {questions.map((q, i) => (
          <button
            key={q.id}
            onClick={() => onGo(i)}
            aria-label={`Question ${q.number}${isAnswered(q) ? ", answered" : ""}${q.flagged ? ", marked for review" : ""}`}
            className={cn(
              "relative rounded-lg border font-semibold tabular-nums",
              large ? "h-14 text-lg" : "h-10 text-sm",
              i === current ? "border-primary ring-2 ring-primary" : "border-border",
              isAnswered(q) ? "bg-primary text-white" : "bg-surface",
            )}
          >
            {q.number}
            {q.flagged && <span className="absolute -right-1 -top-1 h-3 w-3 rounded-full border-2 border-surface bg-warning" />}
          </button>
        ))}
      </div>
      <div className="mt-4 space-y-1 text-xs text-muted">
        <p className="flex items-center gap-2"><span className="h-3 w-3 rounded bg-primary" /> Answered</p>
        <p className="flex items-center gap-2"><span className="h-3 w-3 rounded border border-border" /> Not answered</p>
        <p className="flex items-center gap-2"><span className="h-3 w-3 rounded-full bg-warning" /> Marked for review</p>
      </div>
    </div>
  );
}
