"use client";

import Link from "next/link";
import { use, useState } from "react";

import { Histogram } from "@/components/charts/histogram";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { Alert, Badge, Empty, PageHeader, Spinner, Stat } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { downloadCsv } from "@/lib/admin";
import { post } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { ExamQuestion } from "@/lib/types";

interface Analytics {
  exam: { id: number; title: string; status: string; total_marks: string; pass_marks: string };
  enrolled: number; started: number; submitted: number; in_progress: number; pending_manual: number;
  average: number | null; highest: string | null; lowest: string | null; pass_rate: number | null;
  distribution: { range: string; count: number }[];
  per_question: { question_id: number; text: string; type: string; difficulty: string; chapter: string; served: number; answered: number; correct: number; accuracy: number; avg_marks_pct: number }[];
  per_section: { section_id: number; section: string; submitted: number; average: number | null; pass_rate: number | null; published: boolean }[];
}
interface SheetRow { attempt_id: number; roll_no: string; name: string; section: string; status: string; submit_reason: string; score: string | null; max_score: string; percentage: number; passed: boolean; rank: number | null; grading_status: string; flag_count: number }
interface MarkRow { answer_id: number; attempt_id: number; question_id: number; question_text: string; explanation: string; max_marks: string; text: string; marks_awarded: string | null }

export default function ExamResultsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const stats = useApi<Analytics>(`/admin/exams/${id}/analytics`);
  const sheet = useApi<SheetRow[]>(`/admin/exams/${id}/attempts`);
  const marking = useApi<{ results: MarkRow[]; pending: number }>(`/admin/exams/${id}/marking`);
  const [fixing, setFixing] = useState<number | null>(null);
  const [showAnswers, setShowAnswers] = useState(true);
  const action = useAction();
  const [notice, setNotice] = useState<string | null>(null);
  const reloadAll = () => Promise.all([stats.reload(), sheet.reload(), marking.reload()]);

  if (stats.loading && !stats.data) return <Spinner />;
  if (stats.error || !stats.data) return <Alert>{stats.error?.message}</Alert>;
  const a = stats.data;

  async function publish(sectionIds?: number[]) {
    setNotice(null);
    const res = await action.run(() => post<{ published_sections: number[] }>(`/admin/exams/${id}/publish`, { section_ids: sectionIds ?? [], show_answers: showAnswers }));
    if (res) setNotice("Published. Students in those sections can now see their results.");
    await reloadAll();
  }
  async function unpublish(sectionId: number) {
    const reason = prompt("Reason for hiding these results again:");
    if (!reason) return;
    await action.run(() => post(`/admin/exams/${id}/unpublish`, { section_ids: [sectionId], reason }));
    await reloadAll();
  }

  return (
    <>
      <PageHeader
        title={`Results · ${a.exam.title}`}
        description={`Status: ${a.exam.status} · total ${a.exam.total_marks} · pass ${a.exam.pass_marks}`}
        action={
          <>
            <Link href={`/admin/exams/${id}/monitor`}><Button variant="outline">Monitor</Button></Link>
            <Button variant="outline" onClick={() => sheet.data && downloadCsv(`results-${id}.csv`, sheet.data as unknown as Record<string, unknown>[])}>Export CSV</Button>
          </>
        }
      />
      <Alert className="mb-4">{action.error}</Alert>
      <Alert tone="success" className="mb-4">{notice}</Alert>

      <div className="mb-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Submitted" value={`${a.submitted}/${a.enrolled}`} hint={a.in_progress ? `${a.in_progress} still writing` : undefined} />
        <Stat label="Average" value={fmtNum(a.average)} />
        <Stat label="Highest" value={fmtNum(a.highest)} />
        <Stat label="Lowest" value={fmtNum(a.lowest)} />
        <Stat label="Pass rate" value={a.pass_rate === null ? "—" : `${a.pass_rate}%`} />
        <Stat label="To mark" value={a.pending_manual} hint="short answers" />
      </div>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Score distribution" />
          <CardBody>{a.submitted ? <Histogram buckets={a.distribution} /> : <Empty title="No submissions yet" />}</CardBody>
        </Card>
        <Card>
          <CardHeader title="Publish" description="Results stay hidden from students until published for their section." />
          <CardBody className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={showAnswers} onChange={(e) => setShowAnswers(e.target.checked)} /> Show per-question review with explanations
            </label>
            <Table>
              <THead><tr><Th>Section</Th><Th>Submitted</Th><Th>Average</Th><Th>Pass rate</Th><Th className="text-right" /></tr></THead>
              <TBody>
                {a.per_section.map((s) => (
                  <tr key={s.section_id}>
                    <Td>{s.section}</Td>
                    <Td>{s.submitted}</Td>
                    <Td>{fmtNum(s.average)}</Td>
                    <Td>{s.pass_rate === null ? "—" : `${s.pass_rate}%`}</Td>
                    <Td className="text-right">
                      {s.published ? (
                        <span className="space-x-2"><Badge tone="success">Published</Badge><button className="text-xs text-muted hover:text-danger" onClick={() => unpublish(s.section_id)}>Hide</button></span>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => publish([s.section_id])} loading={action.busy}>Publish</Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </TBody>
            </Table>
            <Button onClick={() => publish()} loading={action.busy} disabled={a.per_section.every((s) => s.published)}>Publish to all sections</Button>
            <p className="text-xs text-muted">Check the answer key and analytics first. Publishing is refused while the window is open, anyone is still writing, or short answers are unmarked.</p>
          </CardBody>
        </Card>
      </div>

      {marking.data && marking.data.results.length > 0 && <MarkingCard rows={marking.data.results} onMarked={reloadAll} />}

      <Card className="mb-6">
        <CardHeader title="Per-question accuracy" description="Lowest accuracy first — a very low score often means a wrong answer key." />
        <Table>
          <THead><tr><Th>Question</Th><Th>Chapter</Th><Th>Level</Th><Th className="text-right">Answered</Th><Th className="text-right">Correct</Th><Th className="text-right">Accuracy</Th><Th /></tr></THead>
          <TBody>
            {a.per_question.map((q) => (
              <tr key={q.question_id}>
                <Td className="max-w-md"><p className="line-clamp-2">{q.text}</p></Td>
                <Td className="text-xs">{q.chapter}</Td>
                <Td className="text-xs">{q.difficulty}</Td>
                <Td className="text-right tabular-nums">{q.answered}/{q.served}</Td>
                <Td className="text-right tabular-nums">{q.correct}</Td>
                <Td className="text-right tabular-nums"><span className={q.accuracy < 25 ? "font-semibold text-danger" : undefined}>{q.accuracy}%</span></Td>
                <Td className="text-right">{q.type !== "short_answer" && <Button size="sm" variant="ghost" onClick={() => setFixing(q.question_id)}>Fix key</Button>}</Td>
              </tr>
            ))}
          </TBody>
        </Table>
      </Card>

      <Card>
        <CardHeader title="Result sheet" />
        <Table>
          <THead><tr><Th>Roll no.</Th><Th>Name</Th><Th>Section</Th><Th className="text-right">Score</Th><Th className="text-right">%</Th><Th>Result</Th><Th className="text-right">Rank</Th><Th>Flags</Th><Th /></tr></THead>
          <TBody>
            {sheet.data?.map((r) => (
              <tr key={r.attempt_id}>
                <Td className="font-mono">{r.roll_no}</Td>
                <Td>{r.name}</Td>
                <Td>{r.section}</Td>
                <Td className="text-right tabular-nums">{r.status === "submitted" ? `${fmtNum(r.score)}/${fmtNum(r.max_score)}` : <Badge tone="primary">writing</Badge>}</Td>
                <Td className="text-right tabular-nums">{r.percentage}%</Td>
                <Td>{r.grading_status === "pending_manual" ? <Badge tone="warning">to mark</Badge> : r.passed ? <Badge tone="success">pass</Badge> : <Badge tone="danger">fail</Badge>}</Td>
                <Td className="text-right tabular-nums">{r.rank ?? "—"}</Td>
                <Td>{r.flag_count > 0 ? <Badge tone={r.flag_count >= 3 ? "danger" : "warning"}>{r.flag_count}</Badge> : "0"}</Td>
                <Td className="text-right"><Link href={`/admin/attempts/${r.attempt_id}`} className="text-sm text-primary">Review</Link></Td>
              </tr>
            ))}
          </TBody>
        </Table>
      </Card>

      <FixKeyDialog examId={id} questionId={fixing} onClose={() => setFixing(null)} onDone={(n) => { setFixing(null); setNotice(`Answer key fixed; ${n} attempts re-graded.`); void reloadAll(); }} />
    </>
  );
}

function MarkingCard({ rows, onMarked }: { rows: MarkRow[]; onMarked: () => void }) {
  const [marks, setMarks] = useState<Record<number, string>>({});
  const action = useAction();
  return (
    <Card className="mb-6">
      <CardHeader title={`Marking · ${rows.length} short answers`} description="Students are anonymous here; marks are audited." />
      <CardBody className="space-y-4">
        <Alert>{action.error}</Alert>
        {rows.map((r) => (
          <div key={r.answer_id} className="rounded-lg border border-border p-3">
            <p className="text-sm font-medium">{r.question_text}</p>
            {r.explanation && <p className="mb-2 text-xs text-muted">Model answer: {r.explanation}</p>}
            <p className="mb-3 whitespace-pre-line rounded bg-subtle p-2 text-sm">{r.text || <i className="text-muted">blank</i>}</p>
            <div className="flex items-center gap-2">
              <Input className="h-9 w-24" placeholder={`0–${r.max_marks}`} value={marks[r.answer_id] ?? ""} onChange={(e) => setMarks({ ...marks, [r.answer_id]: e.target.value })} />
              <span className="text-sm text-muted">/ {r.max_marks}</span>
              <Button size="sm" disabled={!marks[r.answer_id]} onClick={() => action.run(() => post(`/admin/answers/${r.answer_id}/mark`, { marks_awarded: marks[r.answer_id] })).then((x) => x !== undefined && onMarked())}>Save</Button>
            </div>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

function FixKeyDialog({ examId, questionId, onClose, onDone }: { examId: string; questionId: number | null; onClose: () => void; onDone: (n: number) => void }) {
  const paper = useApi<{ questions: ExamQuestion[] }>(questionId ? `/admin/exams/${examId}/paper` : null);
  const q = paper.data?.questions.find((x) => x.question === questionId)?.question_detail;
  const [chosen, setChosen] = useState<number[] | null>(null);
  const [numeric, setNumeric] = useState("");
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  if (!questionId) return null;
  const current = chosen ?? q?.options.filter((o) => o.is_correct).map((o) => o.id!) ?? [];

  async function save() {
    const body = q?.type === "numeric" ? { question_id: questionId, numeric_answer: numeric, reason } : { question_id: questionId, correct_option_ids: current, reason };
    const res = await run(() => post<{ regraded_attempts: number }>(`/admin/exams/${examId}/regrade`, body));
    if (res) {
      setChosen(null);
      setReason("");
      onDone(res.regraded_attempts);
    }
  }

  return (
    <Dialog open onClose={onClose} title="Fix answer key and re-grade" footer={<><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={reason.trim().length < 3}>Re-grade everyone</Button></>}>
      {!q ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          <p className="font-medium">{q.text}</p>
          {q.type === "numeric" ? (
            <Field label={`Correct value (now ${q.numeric_answer})`}><Input value={numeric} onChange={(e) => setNumeric(e.target.value)} /></Field>
          ) : (
            <div className="space-y-2">
              {q.options.map((o) => (
                <label key={o.id} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm">
                  <input
                    type={q.type === "mcq_multi" ? "checkbox" : "radio"}
                    name="key"
                    checked={current.includes(o.id!)}
                    onChange={(e) => setChosen(q.type === "mcq_multi" ? (e.target.checked ? [...current, o.id!] : current.filter((x) => x !== o.id)) : [o.id!])}
                  />
                  {o.text}
                </label>
              ))}
            </div>
          )}
          <Field label="Reason (saved in the audit log)"><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          <Alert>{error}</Alert>
        </div>
      )}
    </Dialog>
  );
}

