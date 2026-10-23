"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, get } from "./api";

/** Minimal data hook: fetches `path` (skips when null), exposes reload(). */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const latest = useRef(path);

  const load = useCallback(async () => {
    if (path === null) return;
    latest.current = path;
    setLoading(true);
    try {
      const result = await get<T>(path);
      if (latest.current === path) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (latest.current === path) setError(e instanceof ApiError ? e : new ApiError(0, null, "Network error"));
    } finally {
      if (latest.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}

/** Run an action with busy/error state, for buttons and forms. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

/** Server time offset in ms (server − client), so countdowns use the server's clock. */
export function serverOffset(serverTime: string) {
  return new Date(serverTime).getTime() - Date.now();
}
