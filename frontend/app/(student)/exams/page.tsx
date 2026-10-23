"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert, Badge, Empty, PageHeader, Spinner, type Tone } from "@/components/ui/misc";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { UpcomingExam } from "@/lib/types";

function statusOf(e: UpcomingExam): { label: string; tone: Tone } {
  if (e.attempt?.status === "submitted") return { label: e.status === "published" ? "Result out" : "Submitted", tone: "success" };
  if (e.attempt?.status === "in_progress" && e.status === "live") return { label: "In progress", tone: "warning" };
  if (e.status === "live") return { label: "Live now", tone: "primary" };
  if (e.status === "upcoming") return { label: "Upcoming", tone: "neutral" };
  return { label: "Closed", tone: "neutral" };
}

export default function ExamsPage() {
  const { data, error, loading } = useApi<{ results: UpcomingExam[] }>("/exams/upcoming");
  if (loading) return <Spinner />;
  if (error) return <Alert>{error.message}</Alert>;
  const exams = data?.results ?? [];

  return (
    <>
      <PageHeader title="Exams" description="Exams set for your section" />
      {!exams.length && <Empty title="No exams right now">Scheduled exams will show up here.</Empty>}
      <div className="space-y-3">
        {exams.map((e) => {
          const s = statusOf(e);
          const canEnter = e.status === "live" && e.attempt?.status !== "submitted";
          return (
            <Card key={e.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-semibold">{e.title}</p>
                  <Badge tone={s.tone}>{s.label}</Badge>
                </div>
                <p className="text-sm text-muted">
                  {e.subject} · {e.duration_min} min · {e.total_marks} marks · {fmtDateTime(e.start_at)} – {fmtDateTime(e.end_at)}
                </p>
              </div>
              {canEnter && (
                <Link href={`/exams/${e.id}/attempt`}>
                  <Button variant={e.attempt ? "outline" : "primary"}>{e.attempt ? "Resume" : "Start"}</Button>
                </Link>
              )}
              {e.status === "published" && e.attempt?.status === "submitted" && (
                <Link href={`/results/${e.id}`}>
                  <Button variant="outline">View result</Button>
                </Link>
              )}
            </Card>
          );
        })}
      </div>
    </>
  );
}
