"use client";

import Link from "next/link";

import { Card, CardHeader } from "@/components/ui/card";
import { Alert, Badge, Empty, PageHeader, Spinner, Stat } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { EXAM_STATUS_TONE, examLinks } from "@/lib/admin";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Exam, Paginated, Student } from "@/lib/types";

export default function AdminDashboard() {
  const exams = useApi<Paginated<Exam>>("/admin/exams?page_size=100");
  const students = useApi<Paginated<Student>>("/admin/students?page_size=1&is_active=true");
  if (exams.loading || students.loading) return <Spinner />;
  if (exams.error) return <Alert>{exams.error.message}</Alert>;
  const all = exams.data?.results ?? [];
  const live = all.filter((e) => e.effective_status === "live");
  const upcoming = all.filter((e) => e.effective_status === "upcoming");
  const toPublish = all.filter((e) => ["closed", "graded"].includes(e.effective_status));

  return (
    <>
      <PageHeader title="Dashboard" />
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Active students" value={students.data?.count ?? "—"} />
        <Stat label="Live exams" value={live.length} />
        <Stat label="Upcoming exams" value={upcoming.length} />
        <Stat label="Awaiting publish" value={toPublish.length} />
      </div>
      <Card>
        <CardHeader title="Exams needing attention" action={<Link href="/admin/exams/new" className="text-sm font-medium text-primary">New exam</Link>} />
        {[...live, ...upcoming, ...toPublish].length === 0 ? (
          <div className="p-5"><Empty title="Nothing live or upcoming" /></div>
        ) : (
          <Table>
            <THead>
              <tr><Th>Exam</Th><Th>Sections</Th><Th>Window</Th><Th>Status</Th><Th /></tr>
            </THead>
            <TBody>
              {[...live, ...upcoming, ...toPublish].map((e) => {
                const links = examLinks(e);
                return (
                  <tr key={e.id}>
                    <Td><p className="font-medium">{e.title}</p><p className="text-xs text-muted">Class {e.grade} · {e.subject_name}</p></Td>
                    <Td>{e.sections_label.join(", ")}</Td>
                    <Td className="text-xs">{fmtDateTime(e.start_at)} – {fmtDateTime(e.end_at)}</Td>
                    <Td><Badge tone={EXAM_STATUS_TONE[e.effective_status]}>{e.effective_status}</Badge></Td>
                    <Td className="text-right">
                      <Link href={e.effective_status === "live" ? links.monitor : e.effective_status === "upcoming" ? links.edit : links.results} className="text-sm font-medium text-primary">
                        {e.effective_status === "live" ? "Monitor" : e.effective_status === "upcoming" ? "Open" : "Results"}
                      </Link>
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
