"use client";

import Link from "next/link";

import { BarList } from "@/components/charts/bar-list";
import { ScoreTrend } from "@/components/charts/score-trend";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, Badge, Empty, PageHeader, Progress, Spinner, Stat } from "@/components/ui/misc";
import { fmtDateTime, fmtDuration } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Progress as ProgressData } from "@/lib/types";

export default function DashboardPage() {
  const { data, error, loading } = useApi<ProgressData>("/me/progress");
  if (loading) return <Spinner />;
  if (error || !data) return <Alert>{error?.message ?? "Could not load your dashboard."}</Alert>;

  const totalVideos = data.subjects.reduce((n, s) => n + s.videos, 0);
  const doneVideos = data.subjects.reduce((n, s) => n + s.completed, 0);
  const latest = data.latest_results[0];

  return (
    <>
      <PageHeader title={`Hello, ${data.student.name.split(" ")[0] || data.student.roll_no}`} description={`Class ${data.student.section} · Roll ${data.student.roll_no}`} />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Lessons completed" value={`${doneVideos}/${totalVideos}`} />
        <Stat label="Upcoming exams" value={data.upcoming_exams.length} />
        <Stat label="Latest score" value={latest ? `${Math.round(latest.percentage)}%` : "—"} hint={latest?.title} />
        <Stat label="Rank in section" value={data.rank?.rank ? `#${data.rank.rank}` : "—"} hint={data.rank ? `of ${data.rank.section_size} · ${data.rank.exam}` : undefined} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {data.upcoming_exams.length > 0 && (
            <Card>
              <CardHeader title="Upcoming exams" action={<Link href="/exams" className="text-sm font-medium text-primary">All exams</Link>} />
              <CardBody className="divide-y divide-border p-0">
                {data.upcoming_exams.map((e) => (
                  <div key={e.id} className="flex items-center justify-between gap-4 px-5 py-3">
                    <div>
                      <p className="font-medium">{e.title}</p>
                      <p className="text-sm text-muted">{e.subject} · {fmtDateTime(e.start_at)}</p>
                    </div>
                    {e.status === "live" ? (
                      <Link href="/exams" className="rounded-lg bg-success px-3 py-1.5 text-sm font-medium text-white">Start</Link>
                    ) : (
                      <Badge>Upcoming</Badge>
                    )}
                  </div>
                ))}
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Score trend" description="Your percentage in each published exam" />
            <CardBody>
              {data.score_trend.length ? (
                <ScoreTrend points={data.score_trend.map((p) => ({ label: p.title, date: p.date, value: p.percentage }))} />
              ) : (
                <Empty title="No results yet">Your scores will appear here after results are published.</Empty>
              )}
            </CardBody>
          </Card>

          {data.continue_watching.length > 0 && (
            <Card>
              <CardHeader title="Continue watching" />
              <CardBody className="grid gap-3 sm:grid-cols-2">
                {data.continue_watching.map((v) => (
                  <Link key={v.video_id} href={`/videos/0/${v.video_id}`} className="rounded-lg border border-border p-3 hover:border-primary">
                    <p className="font-medium">{v.title}</p>
                    <p className="mb-2 text-sm text-muted">{v.subject} · {fmtDuration(v.last_position_s)} of {fmtDuration(v.duration_s)}</p>
                    <Progress value={(100 * v.last_position_s) / v.duration_s} />
                  </Link>
                ))}
              </CardBody>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Lessons by subject" />
            <CardBody>
              {data.subjects.length ? (
                <BarList
                  ariaLabel="Lesson completion by subject"
                  items={data.subjects.map((s) => ({ key: s.subject_id, label: s.subject, value: s.percent, detail: `${s.completed} of ${s.videos} lessons done` }))}
                />
              ) : (
                <Empty title="No lessons yet" />
              )}
            </CardBody>
          </Card>
          {data.weak_chapters.length > 0 && (
            <Card>
              <CardHeader title="Chapters to practise" description="Lowest marks across your exams" />
              <CardBody>
                <BarList ariaLabel="Weakest chapters" items={data.weak_chapters.map((c) => ({ key: c.chapter_id, label: c.chapter, value: c.percentage, detail: `${c.percentage}% of available marks` }))} />
              </CardBody>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
