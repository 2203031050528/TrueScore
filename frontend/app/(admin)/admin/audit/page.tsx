"use client";

import { Fragment, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Alert, PageHeader, Spinner } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AuditEntry, Paginated } from "@/lib/types";

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ page: String(page), page_size: "50", ...(action && { action }), ...(entity && { entity }) });
  const { data, error, loading } = useApi<Paginated<AuditEntry>>(`/admin/audit?${qs}`);
  const [open, setOpen] = useState<number | null>(null);

  return (
    <>
      <PageHeader title="Audit log" description="Every admin action, append-only." />
      <div className="mb-4 flex flex-wrap gap-3">
        <Input className="w-56" placeholder="Action, e.g. exam.regrade" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} />
        <Input className="w-48" placeholder="Entity, e.g. attempts" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }} />
      </div>
      <Alert>{error?.message}</Alert>
      <Card>
        {loading && !data ? (
          <Spinner />
        ) : (
          <Table>
            <THead><tr><Th>When</Th><Th>Who</Th><Th>Action</Th><Th>Entity</Th><Th>Reason</Th><Th>IP</Th></tr></THead>
            <TBody>
              {data?.results.map((e) => (
                <Fragment key={e.id}>
                  <tr className="cursor-pointer hover:bg-subtle" onClick={() => setOpen(open === e.id ? null : e.id)}>
                    <Td className="whitespace-nowrap text-xs">{fmtDateTime(e.at)}</Td>
                    <Td>{e.actor_username ?? "system"}</Td>
                    <Td className="font-mono text-xs">{e.action}</Td>
                    <Td className="text-xs">{e.entity}#{e.entity_id}</Td>
                    <Td className="max-w-64 truncate text-xs">{e.reason}</Td>
                    <Td className="text-xs text-muted">{e.ip}</Td>
                  </tr>
                  {open === e.id && (
                    <tr>
                      <Td colSpan={6} className="bg-subtle">
                        <div className="grid gap-3 text-xs md:grid-cols-2">
                          <pre className="overflow-x-auto whitespace-pre-wrap"><b>Before</b>{"\n"}{JSON.stringify(e.before, null, 2)}</pre>
                          <pre className="overflow-x-auto whitespace-pre-wrap"><b>After</b>{"\n"}{JSON.stringify(e.after, null, 2)}</pre>
                        </div>
                      </Td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <div className="mt-4 flex justify-end gap-2">
        <Button size="sm" variant="outline" disabled={!data?.previous} onClick={() => setPage(page - 1)}>Previous</Button>
        <Button size="sm" variant="outline" disabled={!data?.next} onClick={() => setPage(page + 1)}>Next</Button>
      </div>
    </>
  );
}
