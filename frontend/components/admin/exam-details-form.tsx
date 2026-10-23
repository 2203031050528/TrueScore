"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { useClasses, useSubjects } from "@/lib/admin";
import { ApiError, api } from "@/lib/api";
import { fromLocalInput, toLocalInput } from "@/lib/format";
import type { Exam } from "@/lib/types";

/** Create or edit exam details. When the paper is locked only title, instructions and end time stay editable. */
export function ExamDetailsForm({ exam, onSaved }: { exam?: Exam; onSaved: (e: Exam) => void }) {
  const locked = Boolean(exam && exam.status !== "draft");
  const classes = useClasses();
  const [classId, setClassId] = useState(exam ? String(exam.school_class) : "");
  const subjects = useSubjects(classId || null);
  const [v, setV] = useState({
    title: exam?.title ?? "",
    subject: exam ? String(exam.subject) : "",
    start_at: toLocalInput(exam?.start_at),
    end_at: toLocalInput(exam?.end_at),
    duration_min: String(exam?.duration_min ?? 30),
    pass_marks: exam?.pass_marks ?? "0",
    instructions: exam?.instructions ?? "",
  });
  const [sections, setSections] = useState<number[]>(exam?.section_ids ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const cls = classes.data?.find((c) => String(c.id) === classId);

  useEffect(() => {
    if (exam) setClassId(String(exam.school_class));
  }, [exam]);

  async function save() {
    setBusy(true);
    setErrors({});
    const full = {
      title: v.title, school_class: Number(classId), subject: Number(v.subject), start_at: fromLocalInput(v.start_at), end_at: fromLocalInput(v.end_at),
      duration_min: Number(v.duration_min), pass_marks: v.pass_marks, instructions: v.instructions, section_ids: sections,
    };
    const body = locked ? { title: v.title, instructions: v.instructions, end_at: fromLocalInput(v.end_at) } : full;
    try {
      onSaved(await api<Exam>(exam ? `/admin/exams/${exam.id}` : "/admin/exams", { method: exam ? "PATCH" : "POST", body }));
    } catch (e) {
      if (e instanceof ApiError) setErrors({ detail: e.message, ...e.fieldErrors() });
    } finally {
      setBusy(false);
    }
  }

  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });

  return (
    <div className="space-y-4">
      <Field label="Title" error={errors.title}><Input value={v.title} onChange={set("title")} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Class" error={errors.school_class}>
          <Select value={classId} disabled={locked} onChange={(e) => { setClassId(e.target.value); setSections([]); setV({ ...v, subject: "" }); }}>
            <option value="">—</option>
            {classes.data?.map((c) => <option key={c.id} value={c.id}>Class {c.grade}</option>)}
          </Select>
        </Field>
        <Field label="Subject" error={errors.subject}>
          <Select value={v.subject} disabled={locked} onChange={set("subject")}>
            <option value="">—</option>
            {subjects.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Target sections" error={errors.section_ids}>
        <div className="flex flex-wrap gap-3">
          {cls?.sections.map((s) => (
            <label key={s.id} className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
              <input type="checkbox" disabled={locked} checked={sections.includes(s.id)} onChange={(e) => setSections(e.target.checked ? [...sections, s.id] : sections.filter((x) => x !== s.id))} />
              {s.label}
            </label>
          )) ?? <span className="text-sm text-muted">Choose a class first.</span>}
        </div>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Opens" error={errors.start_at}><Input type="datetime-local" disabled={locked} value={v.start_at} onChange={set("start_at")} /></Field>
        <Field label="Closes" error={errors.end_at} hint={locked ? "Can only be extended." : undefined}><Input type="datetime-local" value={v.end_at} onChange={set("end_at")} /></Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Duration (minutes)" error={errors.duration_min} hint="Late starters get less time: the attempt never runs past the closing time.">
          <Input type="number" min={1} disabled={locked} value={v.duration_min} onChange={set("duration_min")} />
        </Field>
        <Field label="Pass marks" error={errors.pass_marks}><Input disabled={locked} value={v.pass_marks} onChange={set("pass_marks")} /></Field>
      </div>
      <Field label="Instructions"><Textarea value={v.instructions} onChange={set("instructions")} /></Field>
      <Alert>{errors.detail && Object.keys(errors).length === 1 ? errors.detail : errors.non_field_errors}</Alert>
      <Button onClick={save} loading={busy}>{exam ? "Save details" : "Create exam"}</Button>
    </div>
  );
}
