"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";

import { ExamDetailsForm } from "@/components/admin/exam-details-form";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { Alert, Badge, Empty, PageHeader, Spinner } from "@/components/ui/misc";
import { EXAM_STATUS_TONE, examLinks, useSubjects } from "@/lib/admin";
import { del, get, patch, post } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Difficulty, Exam, ExamPart, ExamQuestion, ExamSettings, Paginated, Question } from "@/lib/types";

const DIFFS: Difficulty[] = ["easy", "medium", "hard"];

export default function ExamEditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const exam = useApi<Exam>(`/admin/exams/${id}`);
  const paper = useApi<{ questions: ExamQuestion[] }>(`/admin/exams/${id}/paper`);
  const action = useAction();
  const [notice, setNotice] = useState<string | null>(null);

  if (exam.loading && !exam.data) return <Spinner />;
  if (exam.error || !exam.data) return <Alert>{exam.error?.message}</Alert>;
  const e = exam.data;
  const locked = e.status !== "draft";
  const reload = () => Promise.all([exam.reload(), paper.reload()]);
  const links = examLinks(e);

  async function lifecycle(op: "schedule" | "unschedule" | "generate") {
    setNotice(null);
    const res = await action.run(() => post<Exam | { generated: Record<string, number> }>(`/admin/exams/${id}/${op}`, op === "unschedule" ? { reason: "Edit paper" } : {}));
    if (res) {
      if (op === "schedule") setNotice("Scheduled. The paper is now locked; students in the target sections can start when the window opens.");
      if (op === "generate" && "generated" in res) setNotice(`Generated: ${Object.entries(res.generated).map(([k, n]) => `${k} → ${n}`).join(", ")}`);
      await reload();
    }
  }

  return (
    <>
      <PageHeader
        title={e.title}
        description={
          <span className="flex items-center gap-2">
            Class {e.grade} · {e.subject_name} · <Badge tone={EXAM_STATUS_TONE[e.effective_status]}>{e.effective_status}</Badge>
            {locked && <span>· total {e.total_marks} marks</span>}
          </span>
        }
        action={
          <>
            {!locked && <Button variant="outline" onClick={() => lifecycle("generate")} loading={action.busy}>Generate from rules</Button>}
            {!locked && <Button onClick={() => lifecycle("schedule")} loading={action.busy}>Schedule &amp; lock</Button>}
            {e.status === "scheduled" && e.attempt_count === 0 && <Button variant="outline" onClick={() => lifecycle("unschedule")}>Back to draft</Button>}
            {locked && <Link href={links.monitor}><Button variant="outline">Live monitor</Button></Link>}
            {locked && <Link href={links.results}><Button variant="outline">Results</Button></Link>}
            {!locked && (
              <Button variant="ghost" className="text-danger" onClick={() => confirm("Delete this draft exam?") && action.run(() => del(`/admin/exams/${id}`)).then((r) => r !== undefined && router.push("/admin/exams"))}>
                Delete
              </Button>
            )}
          </>
        }
      />
      <Alert className="mb-4">{action.error}</Alert>
      <Alert tone="success" className="mb-4">{notice}</Alert>
      {locked && <Alert tone="warning" className="mb-4">The paper is locked. Fix a wrong answer key from the Results page (audited re-grade).</Alert>}

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          {e.parts.map((p) => (
            <PartCard key={p.id} exam={e} part={p} questions={(paper.data?.questions ?? []).filter((q) => q.part === p.id)} onChange={reload} />
          ))}
          {!locked && <AddPart examId={e.id} order={e.parts.length + 1} onAdded={reload} />}
          {!e.parts.length && locked && <Empty title="No parts" />}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Details" />
            <CardBody><ExamDetailsForm exam={e} onSaved={() => void exam.reload()} /></CardBody>
          </Card>
          <SettingsCard exam={e} onSaved={() => void exam.reload()} />
        </div>
      </div>
    </>
  );
}

function AddPart({ examId, order, onAdded }: { examId: number; order: number; onAdded: () => void }) {
  const [name, setName] = useState(`Part ${String.fromCharCode(64 + order)}`);
  const action = useAction();
  return (
    <Card>
      <CardBody className="flex flex-wrap items-end gap-3">
        <Field label="New part" className="flex-1"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Button
          variant="outline"
          loading={action.busy}
          onClick={() => action.run(() => post("/admin/exam-parts", { exam: examId, name, order, rule: { easy: 0, medium: 0, hard: 0, chapters: [], per_student: false } })).then(onAdded)}
        >
          Add part
        </Button>
        {action.error && <Alert className="w-full">{action.error}</Alert>}
      </CardBody>
    </Card>
  );
}

function PartCard({ exam, part, questions, onChange }: { exam: Exam; part: ExamPart; questions: ExamQuestion[]; onChange: () => void }) {
  const locked = exam.status !== "draft";
  const subjects = useSubjects(exam.school_class);
  const chapters = subjects.data?.results.find((s) => s.id === exam.subject)?.chapters ?? [];
  const [rule, setRule] = useState(part.rule);
  const [pickOpen, setPickOpen] = useState(false);
  const action = useAction();
  useEffect(() => setRule(part.rule), [part.rule]);

  const counts = DIFFS.reduce((acc, d) => ({ ...acc, [d]: questions.filter((q) => q.question_detail.difficulty === d).length }), {} as Record<Difficulty, number>);
  const saveRule = () => action.run(() => patch(`/admin/exam-parts/${part.id}`, { rule })).then(onChange);

  return (
    <Card>
      <CardHeader
        title={part.name}
        description={
          rule.per_student
            ? `Per-student sets: each student gets ${rule.easy}/${rule.medium}/${rule.hard} (easy/medium/hard) from a pool of ${questions.length}`
            : `${questions.length} questions · ${DIFFS.map((d) => `${counts[d]} ${d}`).join(", ")}`
        }
        action={
          !locked && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setPickOpen(true)}>Add from bank</Button>
              <Button size="sm" variant="ghost" className="text-danger" onClick={() => confirm(`Delete ${part.name}?`) && action.run(() => del(`/admin/exam-parts/${part.id}`)).then(onChange)}>Delete</Button>
            </div>
          )
        }
      />
      <CardBody className="space-y-4">
        {!locked && (
          <div className="rounded-lg bg-subtle p-3">
            <p className="mb-2 text-sm font-medium">Rule (fill this part automatically)</p>
            <div className="flex flex-wrap items-end gap-3">
              {DIFFS.map((d) => (
                <Field key={d} label={`${d[0].toUpperCase()}${d.slice(1)}`} className="w-20">
                  <Input type="number" min={0} value={rule[d]} onChange={(e) => setRule({ ...rule, [d]: Number(e.target.value) })} />
                </Field>
              ))}
              {DIFFS.map((d) => (
                <Field key={`m-${d}`} label={`Marks (${d})`} className="w-24">
                  <Input placeholder="as set" value={rule.marks?.[d] ?? ""} onChange={(e) => setRule({ ...rule, marks: { ...rule.marks, [d]: e.target.value ? Number(e.target.value) : undefined } })} />
                </Field>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {chapters.map((c) => (
                <label key={c.id} className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-xs">
                  <input type="checkbox" checked={rule.chapters.includes(c.id)} onChange={(e) => setRule({ ...rule, chapters: e.target.checked ? [...rule.chapters, c.id] : rule.chapters.filter((x) => x !== c.id) })} />
                  {c.name}
                </label>
              ))}
              <span className="self-center text-xs text-muted">{rule.chapters.length ? "" : "No chapter ticked = all chapters"}</span>
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm">
              <input type="checkbox" checked={rule.per_student} onChange={(e) => setRule({ ...rule, per_student: e.target.checked })} />
              Give each student a different random set drawn from this rule
            </label>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="outline" onClick={saveRule} loading={action.busy}>Save rule</Button>
              <Button size="sm" onClick={async () => { await saveRule(); await action.run(() => post(`/admin/exams/${exam.id}/generate`, { part_id: part.id })); onChange(); }}>Save &amp; generate</Button>
            </div>
          </div>
        )}
        <Alert>{action.error}</Alert>
        {questions.length === 0 ? (
          <Empty title="No questions in this part yet">Generate from the rule or add from the bank.</Empty>
        ) : (
          <ol className="space-y-2">
            {questions.map((eq, i) => (
              <li key={eq.id} className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm">
                <span className="w-6 text-right text-muted">{i + 1}.</span>
                <div className="min-w-0 flex-1">
                  <p>{eq.question_detail.text}</p>
                  <p className="mt-1 text-xs text-muted">
                    {eq.question_detail.type} · {eq.question_detail.difficulty} · {eq.question_detail.chapter_name}
                    {eq.question_detail.options.length > 0 && ` · key: ${eq.question_detail.options.filter((o) => o.is_correct).map((o) => o.text).join(", ")}`}
                    {eq.question_detail.numeric_answer && ` · key: ${eq.question_detail.numeric_answer}`}
                  </p>
                </div>
                <span className="tabular-nums">{eq.marks}</span>
                {!locked && <button className="text-muted hover:text-danger" aria-label="Remove" onClick={() => action.run(() => del(`/admin/exam-questions/${eq.id}`)).then(onChange)}>×</button>}
              </li>
            ))}
          </ol>
        )}
      </CardBody>
      <PickQuestions open={pickOpen} exam={exam} partId={part.id} existing={new Set(questions.map((q) => q.question))} onClose={() => setPickOpen(false)} onAdded={onChange} />
    </Card>
  );
}

function PickQuestions({ open, exam, partId, existing, onClose, onAdded }: { open: boolean; exam: Exam; partId: number; existing: Set<number>; onClose: () => void; onAdded: () => void }) {
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<Question[]>([]);
  const action = useAction();
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      const res = await get<Paginated<Question>>(`/admin/questions?subject_id=${exam.subject}&page_size=50${search ? `&search=${encodeURIComponent(search)}` : ""}`);
      setItems(res.results);
    }, 250);
    return () => clearTimeout(t);
  }, [open, search, exam.subject]);

  return (
    <Dialog open={open} onClose={onClose} title="Add questions from the bank" footer={<Button onClick={onClose}>Done</Button>}>
      <Input placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} className="mb-3" />
      <Alert className="mb-3">{action.error}</Alert>
      <ul className="space-y-2">
        {items.map((q) => (
          <li key={q.id} className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm">
            <div className="flex-1">
              <p>{q.text}</p>
              <p className="text-xs text-muted">{q.type} · {q.difficulty} · {q.chapter_name} · {q.marks} marks</p>
            </div>
            {existing.has(q.id) ? (
              <Badge tone="success">Added</Badge>
            ) : (
              <Button size="sm" variant="outline" onClick={() => action.run(() => post("/admin/exam-questions", { part: partId, question: q.id })).then(onAdded)}>Add</Button>
            )}
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

function SettingsCard({ exam, onSaved }: { exam: Exam; onSaved: () => void }) {
  const [s, setS] = useState<ExamSettings>(exam.settings);
  const [ips, setIps] = useState(exam.settings.ip_allowlist.join(", "));
  const action = useAction();
  useEffect(() => {
    setS(exam.settings);
    setIps(exam.settings.ip_allowlist.join(", "));
  }, [exam.settings]);
  const toggle = (k: keyof ExamSettings, label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={Boolean(s[k])} onChange={(e) => setS({ ...s, [k]: e.target.checked })} /> {label}
    </label>
  );
  const save = () =>
    action.run(() => patch(`/admin/exams/${exam.id}`, { settings: { ...s, ip_allowlist: ips.split(",").map((x) => x.trim()).filter(Boolean) } })).then((r) => r !== undefined && onSaved());

  return (
    <Card>
      <CardHeader title="Exam security" description="Server rules always apply; these add per-exam controls." />
      <CardBody className="space-y-3">
        {toggle("shuffle_questions", "Shuffle question order per student")}
        {toggle("shuffle_options", "Shuffle option order per student")}
        {toggle("require_fullscreen", "Require full screen")}
        <Field label="Auto-submit after this many full-screen exits" hint="0 = only warn and record">
          <Input type="number" min={0} value={s.max_fullscreen_exits} onChange={(e) => setS({ ...s, max_fullscreen_exits: Number(e.target.value) })} />
        </Field>
        <Field label="Access code" hint="Read aloud by the invigilator. Leave empty for none.">
          <Input value={s.access_code} onChange={(e) => setS({ ...s, access_code: e.target.value })} autoComplete="off" />
        </Field>
        <Field label="Allowed networks" hint="IPs or CIDR ranges, comma separated (e.g. the school lab). Empty = anywhere.">
          <Input value={ips} onChange={(e) => setIps(e.target.value)} placeholder="203.0.113.0/24" />
        </Field>
        {toggle("show_answers", "Show answer review to students after publishing")}
        {toggle("require_seb", "Require Safe Exam Browser (lab exams)")}
        {s.require_seb && (
          <Field label="SEB config key"><Input value={s.seb_config_key} onChange={(e) => setS({ ...s, seb_config_key: e.target.value })} /></Field>
        )}
        <Alert>{action.error}</Alert>
        <Button variant="outline" onClick={save} loading={action.busy}>Save security settings</Button>
      </CardBody>
    </Card>
  );
}
