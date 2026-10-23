const dateTime = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" });

export const fmtDateTime = (v?: string | null) => (v ? dateTime.format(new Date(v)) : "—");
export const fmtDate = (v?: string | null) => (v ? dateOnly.format(new Date(v)) : "—");

export function fmtDuration(totalSeconds: number) {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

export const fmtNum = (v: string | number | null | undefined, digits = 2) =>
  v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: digits });

/** datetime-local input value (local time) ⇄ ISO string */
export function toLocalInput(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const off = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - off).toISOString().slice(0, 16);
}
export const fromLocalInput = (v: string) => (v ? new Date(v).toISOString() : null);

export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
