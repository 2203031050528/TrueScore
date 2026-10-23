"use client";

import { useApi } from "./hooks";
import type { Exam, Paginated, SchoolClass, Subject } from "./types";

export function useClasses() {
  return useApi<SchoolClass[]>("/admin/classes");
}

export function useSubjects(classId: number | string | null) {
  return useApi<Paginated<Subject>>(classId ? `/admin/subjects?class_id=${classId}&page_size=100` : null);
}

export const EXAM_STATUS_TONE: Record<string, "neutral" | "primary" | "success" | "warning" | "danger"> = {
  draft: "neutral",
  upcoming: "primary",
  live: "success",
  closed: "warning",
  graded: "warning",
  published: "success",
};

export function examLinks(exam: Pick<Exam, "id" | "status">) {
  return {
    edit: `/admin/exams/${exam.id}/edit`,
    monitor: `/admin/exams/${exam.id}/monitor`,
    results: `/admin/exams/${exam.id}/results`,
  };
}

/** Turns a list of objects into a CSV download (used for one-time passwords). */
export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [headers.join(","), ...rows.map((r) => headers.map((h) => esc(r[h])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
