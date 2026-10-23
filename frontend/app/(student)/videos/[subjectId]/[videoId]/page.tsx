"use client";

import Link from "next/link";
import { use, useState } from "react";

import { VideoPlayer } from "@/components/video/player";
import { Card, CardBody } from "@/components/ui/card";
import { Alert, Badge, Spinner } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import type { StudentVideo } from "@/lib/types";

export default function WatchPage({ params }: { params: Promise<{ subjectId: string; videoId: string }> }) {
  const { videoId } = use(params);
  const { me } = useAuth();
  const { data: video, error, loading } = useApi<StudentVideo>(`/videos/${videoId}`);
  const [completed, setCompleted] = useState<boolean | null>(null);
  if (loading) return <Spinner />;
  if (error || !video) return <Alert>{error?.status === 404 ? "This lesson is not available." : error?.message}</Alert>;
  const done = completed ?? video.progress.completed;

  return (
    <div className="mx-auto max-w-4xl">
      <Link href={`/videos/${video.subject_id}`} className="text-sm text-primary">
        ← {video.subject_name}
      </Link>
      <h1 className="mb-1 mt-2 text-2xl font-semibold">{video.title}</h1>
      <p className="mb-4 flex items-center gap-2 text-sm text-muted">
        {video.chapter_name} {done && <Badge tone="success">Completed</Badge>}
      </p>
      <VideoPlayer
        videoId={video.id}
        startAt={video.progress.completed ? 0 : video.progress.last_position_s}
        watermark={`${me?.full_name ?? ""} · ${me?.profile?.roll_no ?? ""}`}
        onProgress={(p) => setCompleted(p.completed)}
      />
      {video.description && (
        <Card className="mt-6">
          <CardBody className="whitespace-pre-line text-sm">{video.description}</CardBody>
        </Card>
      )}
    </div>
  );
}
