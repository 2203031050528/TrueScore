"use client";

import { use } from "react";

import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, Badge, Empty, PageHeader, Spinner, Stat } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { cn, fmtDateTime, fmtNum } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ReviewQuestion } from "@/lib/types";

interface Review {
  attempt: {
    id: number; student: { id: number; name: string; roll_no: string; section: string }; status: string; submit_reason: string;
    started_at: string; deadline_at: string; submitted_at: string | null; score: string | null; max_score: string; grading_status: string;
    rank: number | null; flag_count: number; fullscreen_exits: number; ip: string | null; user_agent: string;
  };
  flags: { by_type: Record<string, number>; timeline: { type: string; occurred_at: string; client_time: string | null; detail: Record<string, unknown> }[]; answers_changed_last_30s: number };
  questions: ReviewQuestion[];
}

export default function AttemptReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading } = useApi<Review>(`/admin/attempts/${id}`);
  if (loading) return <Spinner />;
  if (error || !data) return <Alert>{error?.message}</Alert>;
  const { attempt: a, flags, questions } = data;

  return (
    <>
      <PageHeader title={`${a.student.name} · ${a.student.roll_no}`} description={`Section ${a.student.section} · attempt #${a.id}`} />
      <div className="mb-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Score" value={a.score === null ? "—" : `${fmtNum(a.score)}/${fmtNum(a.max_score)}`} hint={a.grading_status} />
        <Stat label="Rank" value={a.rank ?? "—"} />
        <Stat label="Flags" value={a.flag_count} />
        <Stat label="Full-screen exits" value={a.fullscreen_exits} />
        <Stat label="Changed in last 30 s" value={flags.answers_changed_last_30s} hint="answers" />
        <Stat label="Submitted" value={a.submit_reason || a.status} hint={fmtDateTime(a.submitted_at)} />
      </div>
      <Alert tone="warning" className="mb-6">
        Flags are evidence for review, not proof of cheating. A browser cannot see a second phone, and a tab switch can be accidental.
      </Alert>
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {questions.map((q) => (
            <Card key={q.question_id}>
              <CardBody>
                <div className="mb-1 flex justify-between text-sm text-muted">
                  <span>Q{q.number} {q.part && `· ${q.part}`}</span>
                  <Badge tone={q.is_correct ? "success" : q.is_correct === false ? "danger" : "neutral"}>{fmtNum(q.marks_awarded ?? 0)}/{fmtNum(q.marks)}</Badge>
                </div>
                <p className="mb-2 font-medium">{q.text}</p>
                {q.options.map((o, i) => (
                  <p key={i} className={cn("rounded px-2 py-1 text-sm", o.is_correct && "bg-success-soft", o.chosen && !o.is_correct && "bg-danger-soft")}>
                    {o.chosen ? "● " : "○ "}{o.text}{o.is_correct && " ✓"}
                  </p>
                ))}
                {q.your_answer?.value !== undefined && <p className="text-sm">Answer: <b>{q.your_answer.value || "—"}</b> (key {q.correct_value})</p>}
                {q.your_answer?.text !== undefined && <p className="whitespace-pre-line rounded bg-subtle p-2 text-sm">{q.your_answer.text || "—"}</p>}
              </CardBody>
            </Card>
          ))}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Session" />
            <CardBody className="space-y-1 text-sm">
              <p>Started: {fmtDateTime(a.started_at)}</p>
              <p>Deadline: {fmtDateTime(a.deadline_at)}</p>
              <p>IP: {a.ip ?? "—"}</p>
              <p className="break-all text-xs text-muted">{a.user_agent}</p>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Flag timeline" description={Object.entries(flags.by_type).map(([k, n]) => `${k} ×${n}`).join(" · ") || undefined} />
            {flags.timeline.length === 0 ? (
              <CardBody><Empty title="No events" /></CardBody>
            ) : (
              <Table>
                <THead><tr><Th>Time</Th><Th>Event</Th></tr></THead>
                <TBody>
                  {flags.timeline.map((e, i) => (
                    <tr key={i}>
                      <Td className="whitespace-nowrap text-xs">{fmtDateTime(e.occurred_at)}</Td>
                      <Td className="text-xs"><span className="font-mono">{e.type}</span>{Object.keys(e.detail ?? {}).length > 0 && <span className="text-muted"> {JSON.stringify(e.detail)}</span>}</Td>
                    </tr>
                  ))}
                </TBody>
              </Table>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
