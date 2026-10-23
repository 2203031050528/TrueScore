"use client";

import Link from "next/link";
import { use } from "react";

import { Card, CardHeader } from "@/components/ui/card";
import { Alert, Badge, Empty, PageHeader, Progress, Spinner } from "@/components/ui/misc";
import { fmtDuration } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { StudentVideo, Subject } from "@/lib/types";

export default function SubjectVideosPage({ params }: { params: Promise<{ subjectId: string }> }) {
  const { subjectId } = use(params);
  const subjects = useApi<Subject[]>("/subjects");
  const videos = useApi<StudentVideo[]>(`/videos?subject=${subjectId}`);
  if (subjects.loading || videos.loading) return <Spinner />;
  if (videos.error) return <Alert>{videos.error.message}</Alert>;
  const subject = subjects.data?.find((s) => String(s.id) === subjectId);

  return (
    <>
      <PageHeader title={subject?.name ?? "Lessons"} description={<Link href="/videos" className="text-primary">← All subjects</Link>} />
      {!subject?.chapters.length && <Empty title="No chapters yet" />}
      <div className="space-y-5">
        {subject?.chapters.map((ch) => {
          const list = (videos.data ?? []).filter((v) => v.chapter === ch.id);
          if (!list.length) return null;
          return (
            <Card key={ch.id}>
              <CardHeader title={ch.name} description={`${list.length} lessons`} />
              <ul className="divide-y divide-border">
                {list.map((v) => (
                  <li key={v.id}>
                    <Link href={`/videos/${subjectId}/${v.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-subtle">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{v.title}</p>
                        <p className="text-sm text-muted">{fmtDuration(v.duration_s)}</p>
                      </div>
                      <div className="w-32">
                        {v.progress.completed ? <Badge tone="success">Completed</Badge> : <Progress value={v.progress.percent} />}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          );
        })}
      </div>
    </>
  );
}
