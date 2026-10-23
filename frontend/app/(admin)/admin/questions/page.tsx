"use client";

import { useState } from "react";

import { QuestionEditor } from "@/components/admin/question-editor";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/form";
import { Alert, Badge, Empty, PageHeader, Spinner } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { useClasses, useSubjects } from "@/lib/admin";
import { ApiError, api, del } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { Paginated, Question } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = { mcq_single: "MCQ", mcq_multi: "MCQ multi", true_false: "T/F", numeric: "Numeric", short_answer: "Short" };
const DIFF_TONE = { easy: "success", medium: "warning", hard: "danger" } as const;

export default function QuestionsPage() {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const subjects = useSubjects(classId || null);
  const [f, setF] = useState({ subject_id: "", chapter_id: "", difficulty: "", type: "", search: "" });
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), page_size: "50", ...(classId && { class_id: classId }) });
  Object.entries(f).forEach(([k, v]) => v && params.set(k, v));
  const list = useApi<Paginated<Question>>(`/admin/questions?${params}`);
  const [editing, setEditing] = useState<Question | null | undefined>(undefined);
  const [importOpen, setImportOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const action = useAction();
  const chapters = subjects.data?.results.find((s) => String(s.id) === f.subject_id)?.chapters ?? [];
  const set = (k: keyof typeof f, v: string) => { setF({ ...f, [k]: v, ...(k === "subject_id" && { chapter_id: "" }) }); setPage(1); };

  return (
    <>
      <PageHeader
        title="Question bank"
        description={list.data ? `${list.data.count} active questions` : undefined}
        action={<><Button variant="outline" onClick={() => setImportOpen(true)}>Import CSV</Button><Button onClick={() => setEditing(null)}>New question</Button></>}
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-32" value={classId} onChange={(e) => { setClassId(e.target.value); set("subject_id", ""); }}>
          <option value="">All classes</option>
          {classes.data?.map((c) => <option key={c.id} value={c.id}>Class {c.grade}</option>)}
        </Select>
        <Select className="w-44" value={f.subject_id} onChange={(e) => set("subject_id", e.target.value)} disabled={!classId}>
          <option value="">All subjects</option>
          {subjects.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
        <Select className="w-44" value={f.chapter_id} onChange={(e) => set("chapter_id", e.target.value)} disabled={!f.subject_id}>
          <option value="">All chapters</option>
          {chapters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Select className="w-32" value={f.difficulty} onChange={(e) => set("difficulty", e.target.value)}>
          <option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
        </Select>
        <Select className="w-36" value={f.type} onChange={(e) => set("type", e.target.value)}>
          <option value="">Any type</option>
          {Object.entries(TYPE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Input className="w-56" placeholder="Search text" value={f.search} onChange={(e) => set("search", e.target.value)} />
      </div>
      <Alert tone="primary" className="mb-4">{notice}</Alert>
      <Alert className="mb-4">{action.error}</Alert>
      <Card>
        {list.loading && !list.data ? (
          <Spinner />
        ) : !list.data?.results.length ? (
          <div className="p-5"><Empty title="No questions match" /></div>
        ) : (
          <Table>
            <THead><tr><Th>Question</Th><Th>Chapter</Th><Th>Type</Th><Th>Level</Th><Th className="text-right">Marks</Th><Th /></tr></THead>
            <TBody>
              {list.data.results.map((q) => (
                <tr key={q.id}>
                  <Td className="max-w-xl">
                    <p className="line-clamp-2">{q.text}</p>
                    <p className="text-xs text-muted">#{q.id}{q.version > 1 && ` · v${q.version}`}{q.locked && " · in a scheduled exam"}</p>
                  </Td>
                  <Td className="text-xs">{q.grade} · {q.subject_name}<br />{q.chapter_name}</Td>
                  <Td>{TYPE_LABEL[q.type]}</Td>
                  <Td><Badge tone={DIFF_TONE[q.difficulty]}>{q.difficulty}</Badge></Td>
                  <Td className="text-right tabular-nums">{q.marks}{Number(q.negative_marks) > 0 && <span className="text-danger"> −{q.negative_marks}</span>}</Td>
                  <Td className="whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(q)}>Edit</Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => confirm("Remove this question? Questions used in exams are deactivated, not deleted.") && action.run(() => del(`/admin/questions/${q.id}`)).then(list.reload)}>Remove</Button>
                  </Td>
                </tr>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <div className="mt-4 flex justify-end gap-2">
        <Button size="sm" variant="outline" disabled={!list.data?.previous} onClick={() => setPage(page - 1)}>Previous</Button>
        <Button size="sm" variant="outline" disabled={!list.data?.next} onClick={() => setPage(page + 1)}>Next</Button>
      </div>
      <QuestionEditor open={editing !== undefined} question={editing ?? null} onClose={() => setEditing(undefined)} onSaved={(msg) => { setEditing(undefined); setNotice(msg ?? null); void list.reload(); }} />
      <ImportQuestions open={importOpen} onClose={() => setImportOpen(false)} onDone={(n) => { setImportOpen(false); setNotice(`${n} questions imported.`); void list.reload(); }} />
    </>
  );
}

function ImportQuestions({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (n: number) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [rowErrors, setRowErrors] = useState<{ row: number; error: string }[]>([]);
  const { busy, error, run } = useAction();
  async function submit() {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    setRowErrors([]);
    const res = await run(async () => {
      try {
        return await api<{ created: number }>("/admin/questions/import", { method: "POST", body: fd });
      } catch (e) {
        if (e instanceof ApiError && Array.isArray(e.data.errors)) setRowErrors(e.data.errors as { row: number; error: string }[]);
        throw e;
      }
    });
    if (res) onDone(res.created);
  }
  return (
    <Dialog open={open} onClose={onClose} title="Import questions from CSV" footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={submit} disabled={!file} loading={busy}>Import</Button></>}>
      <div className="space-y-3 text-sm">
        <p>Columns: <code className="rounded bg-subtle px-1">class,subject,chapter,type,difficulty,text,marks,options,correct</code>, optional <code className="rounded bg-subtle px-1">negative_marks,explanation,tolerance</code>.</p>
        <ul className="list-disc pl-5 text-muted">
          <li>Options separated by <code>|</code>, e.g. <code>2|4|6|8</code></li>
          <li>Correct: letter or number (<code>B</code>, <code>2</code>, or <code>A|C</code> for multi); the value for numeric</li>
          <li>Missing chapters are created; subjects must exist. All-or-nothing.</li>
        </ul>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Alert>{error}</Alert>
        {rowErrors.length > 0 && <ul className="max-h-40 overflow-y-auto rounded-lg bg-danger-soft p-3 text-xs text-danger">{rowErrors.map((e) => <li key={e.row}>Row {e.row}: {e.error}</li>)}</ul>}
      </div>
    </Dialog>
  );
}
