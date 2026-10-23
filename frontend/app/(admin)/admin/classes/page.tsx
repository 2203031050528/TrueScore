"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Alert, Badge, PageHeader, Spinner } from "@/components/ui/misc";
import { useClasses, useSubjects } from "@/lib/admin";
import { del, patch, post } from "@/lib/api";
import { cn } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Paginated } from "@/lib/types";

interface Year { id: number; label: string; is_current: boolean }

export default function ClassesPage() {
  const classes = useClasses();
  const [selected, setSelected] = useState<number | null>(null);
  const action = useAction();
  if (classes.loading) return <Spinner />;
  const cls = classes.data?.find((c) => c.id === selected) ?? classes.data?.[0];

  return (
    <>
      <PageHeader title="Classes & subjects" />
      <Alert className="mb-4">{action.error ?? classes.error?.message}</Alert>
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <Card className="h-fit p-2">
          {classes.data?.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelected(c.id)}
              className={cn("flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm", c.id === cls?.id ? "bg-primary-soft font-medium text-primary" : "hover:bg-subtle")}
            >
              Class {c.grade}
              <span className="text-xs text-muted">{c.sections.length} sec</span>
            </button>
          ))}
        </Card>
        {cls && (
          <div className="space-y-6">
            <Card>
              <CardHeader title={`Class ${cls.grade} sections`} description={cls.simple_mode ? "Simple mode: large buttons, fewer anti-cheat prompts" : undefined} />
              <CardBody className="flex flex-wrap items-center gap-2">
                {cls.sections.map((s) => (
                  <span key={s.id} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm">
                    {s.label}
                    <button
                      className="text-muted hover:text-danger"
                      aria-label={`Delete section ${s.label}`}
                      onClick={() => confirm(`Delete section ${s.label}?`) && action.run(() => del(`/admin/sections/${s.id}`)).then(classes.reload)}
                    >
                      ×
                    </button>
                  </span>
                ))}
                <AddInline placeholder="New section (e.g. C)" onAdd={(name) => action.run(() => post("/admin/sections", { school_class: cls.id, name })).then(classes.reload)} />
              </CardBody>
            </Card>
            <SubjectsCard classId={cls.id} onError={action.setError} />
          </div>
        )}
      </div>
      <YearCard />
    </>
  );
}

function AddInline({ placeholder, onAdd }: { placeholder: string; onAdd: (v: string) => unknown }) {
  const [v, setV] = useState("");
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (v.trim()) void onAdd(v.trim());
        setV("");
      }}
    >
      <Input className="h-9 w-48" placeholder={placeholder} value={v} onChange={(e) => setV(e.target.value)} />
      <Button size="sm" type="submit" variant="outline">Add</Button>
    </form>
  );
}

function SubjectsCard({ classId, onError }: { classId: number; onError: (e: string | null) => void }) {
  const subjects = useSubjects(classId);
  const action = useAction();
  return (
    <Card>
      <CardHeader title="Subjects & chapters" action={<AddInline placeholder="New subject" onAdd={(name) => action.run(() => post("/admin/subjects", { school_class: classId, name })).then(subjects.reload)} />} />
      <CardBody className="space-y-4">
        <Alert>{action.error}</Alert>
        {subjects.data?.results.map((s) => (
          <div key={s.id} className="rounded-lg border border-border p-3">
            <p className="mb-2 font-medium">{s.name}</p>
            <ol className="mb-2 space-y-1 text-sm">
              {s.chapters.map((ch, i) => (
                <li key={ch.id} className="flex items-center gap-2">
                  <span className="w-6 text-right text-muted">{i + 1}.</span>
                  <span className="flex-1">{ch.name}</span>
                  <button
                    className="text-xs text-muted hover:text-foreground"
                    onClick={() => {
                      const name = prompt("Rename chapter", ch.name);
                      if (name) void action.run(() => patch(`/admin/chapters/${ch.id}`, { name })).then(subjects.reload);
                    }}
                  >
                    Rename
                  </button>
                  <button
                    className="text-xs text-muted hover:text-danger"
                    onClick={() =>
                      confirm(`Delete chapter "${ch.name}"?`) &&
                      action.run(() => del(`/admin/chapters/${ch.id}`)).then((r) => {
                        if (r === undefined) onError("A chapter that has videos or questions cannot be deleted.");
                        void subjects.reload();
                      })
                    }
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ol>
            <AddInline placeholder="New chapter" onAdd={(name) => action.run(() => post("/admin/chapters", { subject: s.id, name, order: s.chapters.length + 1 })).then(subjects.reload)} />
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

function YearCard() {
  const years = useApi<Paginated<Year>>("/admin/academic-years");
  const action = useAction();
  const [label, setLabel] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const current = years.data?.results.find((y) => y.is_current);

  async function promote() {
    if (!/^\d{4}-\d{2}$/.test(label)) return action.setError("Use the format 2027-28.");
    if (!confirm(`Promote every student into ${label}? Class 12 students will be graduated (deactivated). This cannot be undone automatically.`)) return;
    const res = await action.run(() => post<{ promoted: number; graduated: number }>("/admin/promote", { new_year_label: label, reason: "Year-end promotion" }));
    if (res) setResult(`${res.promoted} students promoted, ${res.graduated} graduated.`);
    void years.reload();
  }

  return (
    <Card className="mt-6">
      <CardHeader title="Academic year" description="Year-end promotion moves everyone up one class in one action." />
      <CardBody className="space-y-3">
        <p className="text-sm">
          Current year: {current ? <Badge tone="primary">{current.label}</Badge> : <Badge tone="danger">not set</Badge>}
        </p>
        <div className="flex flex-wrap gap-2">
          <Input className="w-40" placeholder="2027-28" value={label} onChange={(e) => setLabel(e.target.value)} />
          <Button variant="danger" onClick={promote} loading={action.busy}>Promote all students</Button>
        </div>
        <Alert>{action.error}</Alert>
        <Alert tone="success">{result}</Alert>
      </CardBody>
    </Card>
  );
}
