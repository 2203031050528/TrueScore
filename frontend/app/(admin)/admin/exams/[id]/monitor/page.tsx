"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { Alert, Badge, PageHeader, Spinner, Stat, type Tone } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { post } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { MonitorRow } from "@/lib/types";

interface MonitorData {
  exam: { id: number; title: string; status: string; start_at: string; end_at: string };
  server_time: string;
  counts: Record<MonitorRow["state"], number>;
  students: MonitorRow[];
}

const STATE: Record<MonitorRow["state"], { label: string; tone: Tone }> = {
  not_started: { label: "Not started", tone: "neutral" },
  in_progress: { label: "In progress", tone: "primary" },
  disconnected: { label: "Disconnected", tone: "warning" },
  submitted: { label: "Submitted", tone: "success" },
};

type Op = "extend" | "terminate" | "reset" | "release-device";
const OP_LABEL: Record<Op, string> = { extend: "Extend time", terminate: "End attempt", reset: "Reset attempt (student can retake)", "release-device": "Release device lock" };

export default function MonitorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, reload } = useApi<MonitorData>(`/admin/exams/${id}/monitor`);
  const [filter, setFilter] = useState("");
  const [target, setTarget] = useState<{ row: MonitorRow; op: Op } | null>(null);

  useEffect(() => {
    const t = setInterval(() => void reload(), 10000);
    return () => clearInterval(t);
  }, [reload]);

  if (!data) return error ? <Alert>{error.message}</Alert> : <Spinner />;
  const rows = data.students.filter((r) => !filter || r.state === filter || (filter === "flagged" && r.flag_count > 0));

  return (
    <>
      <PageHeader
        title={`Live monitor · ${data.exam.title}`}
        description={`${fmtDateTime(data.exam.start_at)} – ${fmtDateTime(data.exam.end_at)} · refreshes every 10 s`}
        action={<Link href={`/admin/exams/${id}/results`}><Button variant="outline">Results</Button></Link>}
      />
      <div className="mb-6 grid gap-3 sm:grid-cols-4">
        {(Object.keys(STATE) as MonitorRow["state"][]).map((k) => <Stat key={k} label={STATE[k].label} value={data.counts[k]} />)}
      </div>
      <div className="mb-4 flex gap-3">
        <Select className="w-48" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">Everyone</option>
          {Object.entries(STATE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          <option value="flagged">Flagged</option>
        </Select>
      </div>
      <Card>
        <Table>
          <THead><tr><Th>Roll no.</Th><Th>Name</Th><Th>Section</Th><Th>State</Th><Th>Progress</Th><Th>Flags</Th><Th>Deadline</Th><Th>Last seen</Th><Th className="text-right">Actions</Th></tr></THead>
          <TBody>
            {rows.map((r) => (
              <tr key={r.student_id} className={r.flag_count >= 3 ? "bg-danger-soft/40" : undefined}>
                <Td className="font-mono">{r.roll_no}</Td>
                <Td>{r.name}</Td>
                <Td>{r.section}</Td>
                <Td><Badge tone={STATE[r.state].tone}>{STATE[r.state].label}</Badge>{r.submit_reason && r.submit_reason !== "student" && <span className="ml-1 text-xs text-muted">({r.submit_reason})</span>}</Td>
                <Td className="tabular-nums">{r.attempt_id ? `${r.answered}/${r.total_questions}` : "—"}</Td>
                <Td>{r.flag_count > 0 ? <Badge tone={r.flag_count >= 3 ? "danger" : "warning"}>{r.flag_count}</Badge> : "0"}</Td>
                <Td className="text-xs">{r.deadline_at ? fmtDateTime(r.deadline_at) : "—"}</Td>
                <Td className="text-xs">{r.last_seen_at ? fmtDateTime(r.last_seen_at) : "—"}</Td>
                <Td className="whitespace-nowrap text-right">
                  {r.attempt_id && (
                    <>
                      <Link href={`/admin/attempts/${r.attempt_id}`} className="mr-2 text-sm text-primary">Review</Link>
                      <Select className="inline-block h-8 w-36 text-xs" value="" onChange={(e) => e.target.value && setTarget({ row: r, op: e.target.value as Op })}>
                        <option value="">Intervene…</option>
                        {r.state !== "submitted" && <option value="extend">Extend time</option>}
                        {r.state !== "submitted" && <option value="terminate">End attempt</option>}
                        {r.state !== "submitted" && <option value="release-device">Release device</option>}
                        <option value="reset">Reset attempt</option>
                      </Select>
                    </>
                  )}
                </Td>
              </tr>
            ))}
          </TBody>
        </Table>
      </Card>
      <InterveneDialog target={target} onClose={() => setTarget(null)} onDone={() => { setTarget(null); void reload(); }} />
    </>
  );
}

function InterveneDialog({ target, onClose, onDone }: { target: { row: MonitorRow; op: Op } | null; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [minutes, setMinutes] = useState("5");
  const { busy, error, run } = useAction();
  useEffect(() => setReason(""), [target]);
  if (!target) return null;
  const { row, op } = target;
  return (
    <Dialog
      open
      onClose={onClose}
      title={`${OP_LABEL[op]} · ${row.name}`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            variant={op === "reset" || op === "terminate" ? "danger" : "primary"}
            loading={busy}
            disabled={reason.trim().length < 3}
            onClick={() => run(() => post(`/admin/attempts/${row.attempt_id}/${op}`, { reason, ...(op === "extend" && { minutes: Number(minutes) }) })).then((r) => r !== undefined && onDone())}
          >
            Confirm
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {op === "reset" && <Alert tone="warning">This deletes the attempt and its answers. The student can start again. The deletion is recorded in the audit log.</Alert>}
        {op === "extend" && <Field label="Extra minutes"><Input type="number" min={1} max={240} value={minutes} onChange={(e) => setMinutes(e.target.value)} /></Field>}
        <Field label="Reason (required, saved in the audit log)"><Input value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /></Field>
        <Alert>{error}</Alert>
      </div>
    </Dialog>
  );
}
