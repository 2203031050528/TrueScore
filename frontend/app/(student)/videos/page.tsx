"use client";

import Link from "next/link";

import { Card } from "@/components/ui/card";
import { Alert, Empty, PageHeader, Progress, Spinner } from "@/components/ui/misc";
import { useApi } from "@/lib/hooks";
import type { StudentVideo, Subject } from "@/lib/types";

export default function VideosPage() {
  const subjects = useApi<Subject[]>("/subjects");
  const videos = useApi<StudentVideo[]>("/videos");
  if (subjects.loading || videos.loading) return <Spinner />;
  if (subjects.error || videos.error) return <Alert>{(subjects.error ?? videos.error)?.message}</Alert>;

  const bySubject = new Map<number, StudentVideo[]>();
  for (const v of videos.data ?? []) bySubject.set(v.subject_id, [...(bySubject.get(v.subject_id) ?? []), v]);

  return (
    <>
      <PageHeader title="Lessons" description="Video lessons for your class" />
      {!subjects.data?.length ? (
        <Empty title="No subjects yet" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {subjects.data.map((s) => {
            const list = bySubject.get(s.id) ?? [];
            const done = list.filter((v) => v.progress.completed).length;
            return (
              <Link key={s.id} href={`/videos/${s.id}`}>
                <Card className="h-full p-5 transition hover:border-primary">
                  <p className="text-lg font-semibold">{s.name}</p>
                  <p className="mb-4 text-sm text-muted">
                    {list.length} lessons · {s.chapters.length} chapters
                  </p>
                  <Progress value={list.length ? (100 * done) / list.length : 0} tone={done && done === list.length ? "success" : "primary"} />
                  <p className="mt-2 text-xs text-muted">{done} completed</p>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
