"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { Alert, Badge, Empty, PageHeader, Spinner } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { downloadCsv, useClasses } from "@/lib/admin";
import { ApiError, api, post } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Paginated, Student } from "@/lib/types";

interface Credential {
  roll_no: string;
  name: string;
  section: string;
  password: string;
}

export default function StudentsPage() {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const [sectionId, setSectionId] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams({ page: String(page), page_size: "50", ...(classId && { class_id: classId }), ...(sectionId && { section_id: sectionId }), ...(search && { search }) });
  const list = useApi<Paginated<Student>>(`/admin/students?${qs}`);
  const [creds, setCreds] = useState<Credential[] | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState<Student | null>(null);
  const action = useAction();

  const sections = classes.data?.flatMap((c) => c.sections) ?? [];
  const sectionOptions = classId ? classes.data?.find((c) => String(c.id) === classId)?.sections ?? [] : sections;

  async function act(s: Student, op: "reset-password" | "suspend" | "unsuspend" | "force-logout") {
    const labels = { "reset-password": "reset the password for", suspend: "suspend", unsuspend: "re-activate", "force-logout": "log out every session of" };
    const reason = window.prompt(`Reason to ${labels[op]} ${s.full_name} (${s.roll_no}):`);
    if (reason === null) return;
    const res = await action.run(() => post<{ initial_password?: string }>(`/admin/students/${s.id}/${op}`, { reason }));
    if (res?.initial_password) setCreds([{ roll_no: s.roll_no, name: s.full_name, section: s.section_label, password: res.initial_password }]);
    void list.reload();
  }

  return (
    <>
      <PageHeader
        title="Students"
        description={list.data ? `${list.data.count} students` : undefined}
        action={
          <>
            <Button variant="outline" onClick={() => setImportOpen(true)}>Import CSV</Button>
            <Button onClick={() => setAddOpen(true)}>Add student</Button>
          </>
        }
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-36" value={classId} onChange={(e) => { setClassId(e.target.value); setSectionId(""); setPage(1); }}>
          <option value="">All classes</option>
          {classes.data?.map((c) => <option key={c.id} value={c.id}>Class {c.grade}</option>)}
        </Select>
        <Select className="w-36" value={sectionId} onChange={(e) => { setSectionId(e.target.value); setPage(1); }}>
          <option value="">All sections</option>
          {sectionOptions.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </Select>
        <Input className="w-64" placeholder="Search name or roll number" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
      </div>
      <Alert className="mb-4">{action.error}</Alert>

      <Card>
        {list.loading && !list.data ? (
          <Spinner />
        ) : !list.data?.results.length ? (
          <div className="p-5"><Empty title="No students found" /></div>
        ) : (
          <Table>
            <THead>
              <tr><Th>Roll no.</Th><Th>Name</Th><Th>Section</Th><Th>Status</Th><Th>Last login</Th><Th className="text-right">Actions</Th></tr>
            </THead>
            <TBody>
              {list.data.results.map((s) => (
                <tr key={s.id}>
                  <Td className="font-mono">{s.roll_no}</Td>
                  <Td>{s.full_name}</Td>
                  <Td>{s.section_label}</Td>
                  <Td>
                    {!s.is_active ? <Badge tone="danger">Suspended</Badge> : s.must_change_password ? <Badge tone="warning">First login pending</Badge> : <Badge tone="success">Active</Badge>}
                  </Td>
                  <Td className="text-xs text-muted">{fmtDateTime(s.last_login)}</Td>
                  <Td className="space-x-1 whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(s, "reset-password")}>Reset password</Button>
                    <Button size="sm" variant="ghost" onClick={() => act(s, "force-logout")}>Log out</Button>
                    {s.is_active ? (
                      <Button size="sm" variant="ghost" className="text-danger" onClick={() => act(s, "suspend")}>Suspend</Button>
                    ) : (
                      <Button size="sm" variant="ghost" onClick={() => act(s, "unsuspend")}>Re-activate</Button>
                    )}
                  </Td>
                </tr>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      {list.data && list.data.count > 50 && (
        <div className="mt-4 flex justify-end gap-2">
          <Button size="sm" variant="outline" disabled={!list.data.previous} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button size="sm" variant="outline" disabled={!list.data.next} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}

      <StudentForm
        open={addOpen || editing !== null}
        student={editing}
        sections={sections}
        onClose={() => { setAddOpen(false); setEditing(null); }}
        onSaved={(cred) => {
          setAddOpen(false);
          setEditing(null);
          if (cred) setCreds([cred]);
          void list.reload();
        }}
      />
      <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} onDone={(c) => { setImportOpen(false); setCreds(c); void list.reload(); void classes.reload(); }} />
      <Dialog
        open={creds !== null}
        onClose={() => setCreds(null)}
        title="One-time passwords"
        footer={
          <>
            <Button variant="outline" onClick={() => creds && downloadCsv("student-passwords.csv", creds as unknown as Record<string, unknown>[])}>Download CSV</Button>
            <Button onClick={() => setCreds(null)}>Done</Button>
          </>
        }
      >
        <Alert tone="warning" className="mb-3">These passwords are shown only once. Hand them out privately; students must change them at first login.</Alert>
        <Table>
          <THead><tr><Th>Roll no.</Th><Th>Name</Th><Th>Section</Th><Th>Password</Th></tr></THead>
          <TBody>
            {creds?.map((c) => (
              <tr key={c.roll_no}><Td className="font-mono">{c.roll_no}</Td><Td>{c.name}</Td><Td>{c.section}</Td><Td className="font-mono">{c.password}</Td></tr>
            ))}
          </TBody>
        </Table>
      </Dialog>
    </>
  );
}

function StudentForm({ open, student, sections, onClose, onSaved }: { open: boolean; student: Student | null; sections: { id: number; label: string }[]; onClose: () => void; onSaved: (c?: Credential) => void }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body = { roll_no: f.get("roll_no"), full_name: f.get("full_name"), section_id: Number(f.get("section_id")), guardian_phone: f.get("guardian_phone") };
    setBusy(true);
    setErrors({});
    try {
      if (student) {
        await api(`/admin/students/${student.id}`, { method: "PATCH", body });
        onSaved();
      } else {
        const res = await post<Student & { initial_password: string }>("/admin/students", body);
        onSaved({ roll_no: res.roll_no, name: res.full_name, section: res.section_label, password: res.initial_password });
      }
    } catch (err) {
      if (err instanceof ApiError) setErrors({ detail: err.message, ...err.fieldErrors() });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={student ? "Edit student" : "Add student"}>
      <form key={student?.id ?? "new"} onSubmit={submit} className="space-y-4">
        <Field label="Roll number" error={errors.roll_no} hint="Also the login name.">
          <Input name="roll_no" defaultValue={student?.roll_no} required />
        </Field>
        <Field label="Full name" error={errors.full_name}>
          <Input name="full_name" defaultValue={student?.full_name} required />
        </Field>
        <Field label="Section" error={errors.section_id}>
          <Select name="section_id" defaultValue={student?.section_id} required>
            {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </Select>
        </Field>
        <Field label="Guardian phone" error={errors.guardian_phone}>
          <Input name="guardian_phone" defaultValue={student?.guardian_phone} />
        </Field>
        <Alert>{errors.detail && !Object.keys(errors).some((k) => k !== "detail") ? errors.detail : null}</Alert>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={busy}>{student ? "Save" : "Create"}</Button>
        </div>
      </form>
    </Dialog>
  );
}

function ImportDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (c: Credential[]) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [rowErrors, setRowErrors] = useState<{ row: number; error: string }[]>([]);
  const { busy, error, run } = useAction();

  async function submit() {
    if (!file) return;
    setRowErrors([]);
    const fd = new FormData();
    fd.append("file", file);
    const res = await run(async () => {
      try {
        return await api<{ created: Credential[] }>("/admin/students/import", { method: "POST", body: fd });
      } catch (e) {
        if (e instanceof ApiError && Array.isArray(e.data.errors)) setRowErrors(e.data.errors as { row: number; error: string }[]);
        throw e;
      }
    });
    if (res) onDone(res.created);
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Import students from CSV"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={submit} disabled={!file} loading={busy}>Import</Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">
        <p>Columns: <code className="rounded bg-subtle px-1">roll_no,name,class,section</code> (optional <code className="rounded bg-subtle px-1">guardian_phone</code>). Class is the grade number, e.g. 8. Missing sections are created.</p>
        <p className="text-muted">Nothing is imported if any row has a problem.</p>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Alert>{error}</Alert>
        {rowErrors.length > 0 && (
          <ul className="max-h-40 overflow-y-auto rounded-lg bg-danger-soft p-3 text-xs text-danger">
            {rowErrors.map((e) => <li key={e.row}>Row {e.row}: {e.error}</li>)}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
