"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Alert } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { cn } from "@/lib/format";

const SPEEDS = [0.75, 1, 1.25, 1.5, 2];
const HEARTBEAT_MS = 15000;

interface Props {
  videoId: number;
  startAt: number;
  watermark: string;
  onProgress?: (p: { seconds_watched: number; completed: boolean }) => void;
}

/** Plays a short-lived signed URL; re-signs on expiry without losing the position. */
export function VideoPlayer({ videoId, startAt, watermark, onProgress }: Props) {
  const ref = useRef<HTMLVideoElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1);
  const played = useRef(0); // seconds actually played since last heartbeat
  const lastTime = useRef<number | null>(null);
  const resumeAt = useRef(startAt);
  const retries = useRef(0);

  const loadUrl = useCallback(async () => {
    try {
      const { url } = await get<{ url: string }>(`/videos/${videoId}/play-url`);
      setSrc(url);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the video.");
    }
  }, [videoId]);

  useEffect(() => {
    void loadUrl();
  }, [loadUrl]);

  const beat = useCallback(
    async (keepalive = false) => {
      const v = ref.current;
      if (!v) return;
      const delta = Math.round(played.current);
      if (delta <= 0 && !keepalive) return;
      played.current = 0;
      try {
        const res = await post<{ seconds_watched: number; completed: boolean }>(`/videos/${videoId}/progress`, {
          position_s: Math.floor(v.currentTime),
          delta_s: delta,
        });
        onProgress?.(res);
      } catch {
        played.current += delta; // retry with the next beat
      }
    },
    [videoId, onProgress],
  );

  useEffect(() => {
    const t = setInterval(() => void beat(), HEARTBEAT_MS);
    const flush = () => document.visibilityState === "hidden" && void beat(true);
    document.addEventListener("visibilitychange", flush);
    return () => {
      clearInterval(t);
      document.removeEventListener("visibilitychange", flush);
      void beat(true);
    };
  }, [beat]);

  function onTimeUpdate() {
    const v = ref.current!;
    if (lastTime.current !== null && !v.paused && !v.seeking) {
      const step = v.currentTime - lastTime.current;
      if (step > 0 && step < 2) played.current += step / v.playbackRate; // wall-clock seconds, not skipped ones
    }
    lastTime.current = v.currentTime;
    resumeAt.current = v.currentTime;
  }

  function onError() {
    // Most often the signed URL expired: re-sign and continue where we were.
    if (retries.current++ < 3) void loadUrl();
    else setError("The video could not be played. Please reload the page.");
  }

  return (
    <div>
      <div className="relative overflow-hidden rounded-xl bg-black" onContextMenu={(e) => e.preventDefault()}>
        {src && (
          <video
            ref={ref}
            src={src}
            controls
            playsInline
            controlsList="nodownload noplaybackrate noremoteplayback"
            disablePictureInPicture
            className="aspect-video w-full"
            onLoadedMetadata={() => {
              const v = ref.current!;
              if (resumeAt.current > 0 && resumeAt.current < v.duration - 2) v.currentTime = resumeAt.current;
              v.playbackRate = speed;
              retries.current = 0;
            }}
            onTimeUpdate={onTimeUpdate}
            onSeeking={() => (lastTime.current = null)}
            onPause={() => void beat()}
            onEnded={() => void beat()}
            onError={onError}
          />
        )}
        <div className="pointer-events-none absolute inset-0 select-none" aria-hidden>
          <span className="watermark-drift absolute left-0 top-0 whitespace-nowrap text-sm font-medium text-white/35 drop-shadow">{watermark}</span>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm">
        <span className="text-muted">Speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => {
              setSpeed(s);
              if (ref.current) ref.current.playbackRate = s;
            }}
            className={cn("rounded-md px-2 py-1 font-medium", s === speed ? "bg-primary text-white" : "bg-subtle hover:bg-border")}
          >
            {s}×
          </button>
        ))}
      </div>
      <Alert className="mt-3">{error}</Alert>
    </div>
  );
}
