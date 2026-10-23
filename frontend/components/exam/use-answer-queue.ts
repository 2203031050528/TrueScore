"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, put } from "@/lib/api";

export type AnswerPayload = { options?: string[]; value?: string; text?: string; flagged?: boolean };

const RETRY_MS = 3000;

/**
 * Every answer is saved as soon as it is chosen. If the network drops, answers queue in localStorage and
 * retry; the server clock keeps running, so going offline buys no extra time.
 */
export function useAnswerQueue(attemptId: number | null, onClosed: (code: string) => void) {
  const key = attemptId ? `ts-answers-${attemptId}` : null;
  const queue = useRef<Record<number, AnswerPayload>>({});
  const [pending, setPending] = useState(0);
  const [offline, setOffline] = useState(false);
  const flushing = useRef(false);

  const persist = useCallback(() => {
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(queue.current));
    } catch {
      /* storage may be unavailable; the in-memory queue still retries */
    }
    setPending(Object.keys(queue.current).length);
  }, [key]);

  const flush = useCallback(async () => {
    if (!attemptId || flushing.current) return;
    flushing.current = true;
    try {
      for (const [qid, payload] of Object.entries(queue.current)) {
        try {
          await put(`/attempts/${attemptId}/answers/${qid}`, payload);
          if (queue.current[Number(qid)] === payload) delete queue.current[Number(qid)];
          setOffline(false);
        } catch (e) {
          if (e instanceof ApiError && e.status === 409) {
            queue.current = {};
            onClosed(e.code ?? "submitted");
            break;
          }
          if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 429) {
            delete queue.current[Number(qid)]; // invalid answer: retrying won't help
            continue;
          }
          setOffline(true);
          break;
        }
      }
    } finally {
      flushing.current = false;
      persist();
    }
  }, [attemptId, onClosed, persist]);

  useEffect(() => {
    if (!key) return;
    try {
      queue.current = JSON.parse(localStorage.getItem(key) ?? "{}");
    } catch {
      queue.current = {};
    }
    persist();
    void flush();
    const t = setInterval(() => Object.keys(queue.current).length && void flush(), RETRY_MS);
    const online = () => void flush();
    window.addEventListener("online", online);
    return () => {
      clearInterval(t);
      window.removeEventListener("online", online);
    };
  }, [key, flush, persist]);

  const save = useCallback(
    (questionId: number, payload: AnswerPayload) => {
      queue.current[questionId] = payload;
      persist();
      void flush();
    },
    [flush, persist],
  );

  const clear = useCallback(() => {
    queue.current = {};
    if (key) {
      try {
        localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
    }
    setPending(0);
  }, [key]);

  return { save, flush, clear, pending, offline };
}
