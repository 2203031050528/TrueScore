"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/format";
import type { PaperQuestion } from "@/lib/types";

import type { AnswerPayload } from "./use-answer-queue";

const TYPE_HINT: Record<PaperQuestion["type"], string> = {
  mcq_single: "Choose one answer",
  mcq_multi: "Choose all correct answers",
  true_false: "True or false",
  numeric: "Type a number",
  short_answer: "Write a short answer",
};

export function QuestionCard({ q, onAnswer, large }: { q: PaperQuestion; onAnswer: (payload: AnswerPayload) => void; large?: boolean }) {
  const chosen = new Set(q.answer?.options ?? []);
  const [text, setText] = useState(q.answer?.text ?? q.answer?.value ?? "");
  useEffect(() => setText(q.answer?.text ?? q.answer?.value ?? ""), [q.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounce typed answers; options save immediately.
  useEffect(() => {
    if (q.type !== "numeric" && q.type !== "short_answer") return;
    const current = q.type === "numeric" ? q.answer?.value ?? "" : q.answer?.text ?? "";
    if (text === current) return;
    const t = setTimeout(() => onAnswer(q.type === "numeric" ? { value: text } : { text }), 700);
    return () => clearTimeout(t);
  }, [text]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggle(id: string) {
    if (q.type === "mcq_multi") {
      const next = new Set(chosen);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      onAnswer({ options: [...next] });
    } else {
      onAnswer({ options: chosen.has(id) ? [] : [id] });
    }
  }

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-center gap-x-3 text-sm text-muted">
        {q.part && <span className="font-medium text-foreground">{q.part}</span>}
        <span>Question {q.number}</span>
        <span>
          {q.marks} mark{Number(q.marks) === 1 ? "" : "s"}
          {Number(q.negative_marks) > 0 && ` · −${q.negative_marks} for a wrong answer`}
        </span>
      </div>
      <p className={cn("mb-2 whitespace-pre-line font-medium leading-relaxed", large ? "text-2xl" : "text-lg")}>{q.text}</p>
      {q.image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={q.image_url} alt="" draggable={false} className="my-4 max-h-80 rounded-lg border border-border" />
      )}
      <p className="mb-4 text-sm text-muted">{TYPE_HINT[q.type]}</p>

      {q.options.length > 0 && (
        <div className={cn("grid gap-3", q.type === "true_false" && "sm:grid-cols-2")}>
          {q.options.map((o) => {
            const on = chosen.has(o.id);
            return (
              <button
                key={o.id}
                onClick={() => toggle(o.id)}
                aria-pressed={on}
                className={cn(
                  "flex w-full items-center gap-3 rounded-xl border-2 px-4 text-left transition-colors",
                  large ? "min-h-20 text-xl" : "min-h-14",
                  on ? "border-primary bg-primary-soft" : "border-border bg-surface hover:border-primary/40",
                )}
              >
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center border-2",
                    q.type === "mcq_multi" ? "rounded" : "rounded-full",
                    on ? "border-primary bg-primary" : "border-muted",
                  )}
                >
                  {on && <span className={cn("bg-white", q.type === "mcq_multi" ? "h-2 w-2 rounded-sm" : "h-2 w-2 rounded-full")} />}
                </span>
                <span>{o.text}</span>
              </button>
            );
          })}
        </div>
      )}
      {q.type === "numeric" && (
        <input
          inputMode="decimal"
          value={text}
          onChange={(e) => setText(e.target.value.replace(/[^0-9.\-/]/g, ""))}
          maxLength={32}
          placeholder="Your answer"
          className={cn("w-full max-w-xs rounded-xl border-2 border-border px-4 focus:border-primary focus:outline-none", large ? "h-16 text-2xl" : "h-12 text-lg")}
        />
      )}
      {q.type === "short_answer" && (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={5000}
          rows={6}
          spellCheck={false}
          placeholder="Write your answer here"
          className="w-full rounded-xl border-2 border-border px-4 py-3 focus:border-primary focus:outline-none"
        />
      )}
    </div>
  );
}
