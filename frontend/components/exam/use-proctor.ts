"use client";

import { useEffect, useRef } from "react";

import { post } from "@/lib/api";

export type ProctorEventType = "tab_switch" | "blur" | "fullscreen_exit" | "paste" | "copy" | "context_menu" | "print" | "offline" | "heartbeat";

export interface LiveState {
  status: "in_progress" | "submitted";
  submit_reason: string;
  deadline_at: string;
  server_time: string;
  fullscreen_exits: number;
}

const HEARTBEAT_MS = 20000;

/**
 * Browser-side deterrents: detect and report. They cannot stop a second phone; the server treats
 * these as evidence for a teacher, not proof. Every response carries the live attempt state, so the
 * page learns about time extensions, termination and auto-submit.
 */
export function useProctor(attemptId: number | null, active: boolean, onState: (s: LiveState) => void) {
  const stateRef = useRef(onState);
  stateRef.current = onState;

  useEffect(() => {
    if (!attemptId || !active) return;
    const send = async (type: ProctorEventType, detail: Record<string, unknown> = {}) => {
      try {
        const s = await post<LiveState>(`/attempts/${attemptId}/events`, { type, detail, occurred_at: new Date().toISOString() });
        stateRef.current(s);
      } catch {
        /* offline: the heartbeat after reconnect resyncs */
      }
    };
    const block = (type: ProctorEventType) => (e: Event) => {
      e.preventDefault();
      void send(type);
    };

    const onVisibility = () => document.visibilityState === "hidden" && void send("tab_switch");
    const onBlur = () => document.visibilityState === "visible" && void send("blur");
    const onPaste = block("paste");
    const onCopy = block("copy");
    const onCut = block("copy");
    const onContext = block("context_menu");
    const onOffline = () => void send("offline");
    const onBeforePrint = () => void send("print");
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && ["p", "s", "u"].includes(k)) {
        e.preventDefault();
        if (k === "p") void send("print");
      }
    };
    const onSelect = (e: Event) => {
      const t = e.target as HTMLElement;
      if (!t.closest?.("input, textarea")) e.preventDefault();
    };
    // Back navigation is blocked during the attempt.
    history.pushState(null, "", location.href);
    const onPop = () => history.pushState(null, "", location.href);

    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    document.addEventListener("paste", onPaste);
    document.addEventListener("copy", onCopy);
    document.addEventListener("cut", onCut);
    document.addEventListener("contextmenu", onContext);
    document.addEventListener("selectstart", onSelect);
    document.addEventListener("keydown", onKey);
    window.addEventListener("offline", onOffline);
    window.addEventListener("beforeprint", onBeforePrint);
    window.addEventListener("popstate", onPop);
    const beat = setInterval(() => void send("heartbeat"), HEARTBEAT_MS);
    void send("heartbeat");

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("paste", onPaste);
      document.removeEventListener("copy", onCopy);
      document.removeEventListener("cut", onCut);
      document.removeEventListener("contextmenu", onContext);
      document.removeEventListener("selectstart", onSelect);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener("beforeprint", onBeforePrint);
      window.removeEventListener("popstate", onPop);
      clearInterval(beat);
    };
  }, [attemptId, active]);
}

/** Reports full-screen exits; returns nothing — the page renders the guard overlay from document state. */
export function useFullscreenWatch(attemptId: number | null, active: boolean, onExit: () => void, onState: (s: LiveState) => void) {
  const exitRef = useRef(onExit);
  const stateRef = useRef(onState);
  exitRef.current = onExit;
  stateRef.current = onState;
  useEffect(() => {
    if (!attemptId || !active) return;
    const onChange = async () => {
      if (document.fullscreenElement) return;
      exitRef.current();
      try {
        stateRef.current(await post<LiveState>(`/attempts/${attemptId}/events`, { type: "fullscreen_exit" }));
      } catch {
        /* ignore */
      }
    };
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, [attemptId, active]);
}

export async function enterFullscreen() {
  try {
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen({ navigationUI: "hide" });
    return true;
  } catch {
    return false;
  }
}
