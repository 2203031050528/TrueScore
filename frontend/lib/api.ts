// Same-origin API client. Tokens live in httpOnly cookies; this file never sees them.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | null,
    message: string,
    public data: Record<string, unknown> = {},
  ) {
    super(message);
  }

  /** First field error from a DRF validation response, if any. */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(this.data)) {
      if (Array.isArray(v) && typeof v[0] === "string") out[k] = v[0];
      else if (typeof v === "string" && k !== "detail" && k !== "code") out[k] = v;
    }
    return out;
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

async function csrfToken(): Promise<string> {
  let token = readCookie("csrftoken");
  if (!token) {
    const res = await fetch("/api/v1/auth/csrf", { credentials: "same-origin" });
    token = ((await res.json()) as { csrfToken: string }).csrfToken;
  }
  return token;
}

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  // Several requests may expire at once; share one refresh call.
  refreshing ??= (async () => {
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": await csrfToken() },
      });
      return res.ok;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** Internal: prevents refresh loops. */
  retried?: boolean;
  keepalive?: boolean;
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = (opts.method ?? (opts.body !== undefined ? "POST" : "GET")).toUpperCase();
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (UNSAFE.has(method)) headers["X-CSRFToken"] = await csrfToken();

  const res = await fetch(`/api/v1${path}`, { method, headers, body, credentials: "same-origin", cache: "no-store", keepalive: opts.keepalive });
  if (res.status === 401 && !opts.retried && !path.startsWith("/auth/")) {
    if (await refreshSession()) return api<T>(path, { ...opts, retried: true });
    if (typeof window !== "undefined") window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  const text = await res.text();
  const data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : res.status === 429 ? "Too many requests. Please wait a moment." : "Something went wrong.";
    if (res.status === 403 && data.code === "password_change_required" && typeof window !== "undefined") {
      window.location.href = "/change-password";
    }
    throw new ApiError(res.status, (data.code as string) ?? null, detail, data);
  }
  return data as T;
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, body: unknown = {}) => api<T>(path, { method: "POST", body });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Uploads a file straight to storage with a presigned URL (the backend never carries the bytes). */
export async function uploadFile(kind: "videos" | "thumbnails" | "questions" | "photos", file: File, onProgress?: (pct: number) => void): Promise<string> {
  const { key, upload } = await post<{ key: string; upload: { url: string; method: string; headers: Record<string, string> } }>(
    "/admin/videos/upload-url",
    { kind, content_type: file.type, size: file.size },
  );
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(upload.method, upload.url);
    Object.entries(upload.headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((100 * e.loaded) / e.total));
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed (${xhr.status})`)));
    xhr.onerror = () => reject(new Error("Upload failed: network error"));
    xhr.send(file);
  });
  return key;
}
