"use client";

import Link from "next/link";
import { use } from "react";

import { Card, CardBody } from "@/components/ui/card";
import { Alert, Badge, Empty, Spinner, Stat } from "@/components/ui/misc";
import { cn, fmtNum } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ResultDetail, ReviewQuestion } from "@/lib/types";

function Review({ q }: { q: ReviewQuestion }) {
  const tone = q.is_correct === true ? "success" : q.is_correct === false ? "danger" : "neutral";
  return (
    <Card>
      <CardBody>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="text-muted">
            {q.part && `${q.part} · `}Question {q.number}
          </span>
          <Badge tone={tone}>
            {fmtNum(q.marks_awarded ?? 0)} / {fmtNum(q.marks)} {q.answered ? "" : "· not answered"}
          </Badge>
        </div>
        <p className="mb-3 whitespace-pre-line font-medium">{q.text}</p>
        {q.image_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={q.image_url} alt="" className="mb-3 max-h-64 rounded-lg border border-border" />
        )}
        {q.options.length > 0 && (
          <ul className="space-y-2">
            {q.options.map((o, i) => (
              <li
                key={i}
                className={cn(
                  "flex items-center justify-between rounded-lg border px-3 py-2 text-sm",
                  o.is_correct ? "border-success bg-success-soft" : o.chosen ? "border-danger bg-danger-soft" : "border-border",
                )}
              >
                <span>{o.text}</span>
                <span className="text-xs font-medium">
                  {o.chosen && "Your answer"}
                  {o.chosen && o.is_correct && " · "}
                  {o.is_correct && "Correct"}
                </span>
              </li>
            ))}
          </ul>
        )}
        {q.type === "numeric" && (
          <p className="text-sm">
            Your answer: <b>{q.your_answer?.value || "—"}</b> · Correct: <b>{fmtNum(q.correct_value ?? null, 4)}</b>
          </p>
        )}
        {q.type === "short_answer" && <p className="whitespace-pre-line rounded-lg bg-subtle p-3 text-sm">{q.your_answer?.text || "—"}</p>}
        {q.explanation && <p className="mt-3 border-l-2 border-primary pl-3 text-sm text-muted">{q.explanation}</p>}
      </CardBody>
    </Card>
  );
}

export default function ResultDetailPage({ params }: { params: Promise<{ examId: string }> }) {
  const { examId } = use(params);
  const { data, error, loading } = useApi<ResultDetail>(`/results/${examId}`);
  if (loading) return <Spinner />;
  if (error?.code === "not_published")
    return <Empty title="Not published yet">Your teacher has not published this result. Check back later.</Empty>;
  if (error || !data) return <Alert>{error?.message}</Alert>;

  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/results" className="text-sm text-primary">← All results</Link>
      <h1 className="mb-1 mt-2 text-2xl font-semibold">{data.title}</h1>
      <p className="mb-6 text-sm text-muted">{data.subject}</p>
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Score" value={`${fmtNum(data.score)}/${fmtNum(data.max_score)}`} />
        <Stat label="Percentage" value={`${data.percentage}%`} />
        <Stat label="Result" value={data.passed ? "Pass" : "Not passed"} hint={`Pass mark ${fmtNum(data.pass_marks)}`} />
        <Stat label="Rank" value={data.rank ? `#${data.rank}` : "—"} hint={`in section of ${data.section_size}`} />
      </div>
      {data.questions ? (
        <div className="space-y-4">
          {data.questions.map((q) => (
            <Review key={q.question_id} q={q} />
          ))}
        </div>
      ) : (
        <Empty title="Answer review is turned off for this exam" />
      )}
    </div>
  );
}
