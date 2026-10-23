"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/form";
import { Alert, Badge, Empty, PageHeader, Spinner } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { EXAM_STATUS_TONE, examLinks, useClasses } from "@/lib/admin";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Exam, Paginated } from "@/lib/types";

export default function ExamsPage() {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const qs = new URLSearchParams({ page_size: "100", ...(classId && { class_id: classId }), ...(status && { status }), ...(search && { search }) });
  const { data, error, loading } = useApi<Paginated<Exam>>(`/admin/exams?${qs}`);

  return (
    <>
      <PageHeader title="Exams" action={<Link href="/admin/exams/new"><Button>New exam</Button></Link>} />
      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-36" value={classId} onChange={(e) => setClassId(e.target.value)}>
          <option value="">All classes</option>
          {classes.data?.map((c) => <option key={c.id} value={c.id}>Class {c.grade}</option>)}
        </Select>
        <Select className="w-36" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option><option value="draft">Draft</option><option value="scheduled">Scheduled</option><option value="graded">Graded</option><option value="published">Published</option>
        </Select>
        <Input className="w-56" placeholder="Search title" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <Alert>{error?.message}</Alert>
      <Card>
        {loading && !data ? (
          <Spinner />
        ) : !data?.results.length ? (
          <div className="p-5"><Empty title="No exams yet" /></div>
        ) : (
          <Table>
            <THead><tr><Th>Exam</Th><Th>Sections</Th><Th>Window</Th><Th>Marks</Th><Th>Status</Th><Th>Attempts</Th><Th className="text-right">Open</Th></tr></THead>
            <TBody>
              {data.results.map((e) => {
                const l = examLinks(e);
                return (
                  <tr key={e.id}>
                    <Td><Link href={l.edit} className="font-medium text-primary">{e.title}</Link><p className="text-xs text-muted">Class {e.grade} · {e.subject_name}</p></Td>
                    <Td className="text-xs">{e.sections_label.join(", ") || "—"}</Td>
                    <Td className="text-xs">{fmtDateTime(e.start_at)}<br />{fmtDateTime(e.end_at)}</Td>
                    <Td className="tabular-nums">{e.status === "draft" ? "—" : e.total_marks}</Td>
                    <Td><Badge tone={EXAM_STATUS_TONE[e.effective_status]}>{e.effective_status}</Badge></Td>
                    <Td className="tabular-nums">{e.attempt_count}</Td>
                    <Td className="space-x-3 whitespace-nowrap text-right text-sm">
                      <Link href={l.edit} className="text-primary">Paper</Link>
                      {e.status !== "draft" && <Link href={l.monitor} className="text-primary">Monitor</Link>}
                      {e.status !== "draft" && <Link href={l.results} className="text-primary">Results</Link>}
                    </Td>
                  </tr>
                );
              })}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
