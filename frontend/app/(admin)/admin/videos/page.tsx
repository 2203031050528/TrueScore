"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Alert, Badge, Empty, PageHeader, Progress, Spinner } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { useClasses, useSubjects } from "@/lib/admin";
import { del, get, patch, post, uploadFile } from "@/lib/api";
import { fmtDuration } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { AdminVideo, Paginated } from "@/lib/types";

function readDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      URL.revokeObjectURL(v.src);
      resolve(Math.round(v.duration) || 0);
    };
    v.onerror = () => resolve(0);
    v.src = URL.createObjectURL(file);
  });
}

export default function AdminVideosPage() {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const subjects = useSubjects(classId || null);
  const qs = new URLSearchParams({ page_size: "100", ...(classId && { class_id: classId }), ...(subjectId && { subject_id: subjectId }) });
  const list = useApi<Paginated<AdminVideo>>(`/admin/videos?${qs}`);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [preview, setPreview] = useState<{ title: string; url: string } | null>(null);
  const action = useAction();

  const toggle = (v: AdminVideo) =>
    action.run(() => patch(`/admin/videos/${v.id}`, { status: v.status === "published" ? "draft" : "published" })).then(list.reload);

  return (
    <>
      <PageHeader title="Videos" description="Students see only published videos of their own class." action={<Button onClick={() => setUploadOpen(true)}>Upload video</Button>} />
      <div className="mb-4 flex flex-wrap gap-3">
        <Select className="w-36" value={classId} onChange={(e) => { setClassId(e.target.value); setSubjectId(""); }}>
          <option value="">All classes</option>
          {classes.data?.map((c) => <option key={c.id} value={c.id}>Class {c.grade}</option>)}
        </Select>
        <Select className="w-48" value={subjectId} onChange={(e) => setSubjectId(e.target.value)} disabled={!classId}>
          <option value="">All subjects</option>
          {subjects.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
      </div>
      <Alert className="mb-4">{action.error}</Alert>
      <Card>
        {list.loading && !list.data ? (
          <Spinner />
        ) : !list.data?.results.length ? (
          <div className="p-5"><Empty title="No videos yet" /></div>
        ) : (
          <Table>
            <THead><tr><Th>Title</Th><Th>Class · Subject · Chapter</Th><Th>Length</Th><Th>Order</Th><Th>Status</Th><Th className="text-right">Actions</Th></tr></THead>
            <TBody>
              {list.data.results.map((v) => (
                <tr key={v.id}>
                  <Td className="font-medium">{v.title}</Td>
                  <Td className="text-xs">{v.grade} · {v.subject_name} · {v.chapter_name}</Td>
                  <Td className="tabular-nums">{fmtDuration(v.duration_s)}</Td>
                  <Td>
                    <Input
                      type="number"
                      className="h-8 w-16"
                      defaultValue={v.order}
                      onBlur={(e) => Number(e.target.value) !== v.order && action.run(() => patch(`/admin/videos/${v.id}`, { order: Number(e.target.value) }))}
                    />
                  </Td>
                  <Td><Badge tone={v.status === "published" ? "success" : "neutral"}>{v.status}</Badge></Td>
                  <Td className="space-x-1 whitespace-nowrap text-right">
                    <Button size="sm" variant="ghost" onClick={async () => setPreview({ title: v.title, url: (await get<{ url: string }>(`/admin/videos/${v.id}/play-url`)).url })}>Preview</Button>
                    <Button size="sm" variant="ghost" onClick={() => toggle(v)}>{v.status === "published" ? "Unpublish" : "Publish"}</Button>
                    <Button size="sm" variant="ghost" className="text-danger" onClick={() => confirm(`Delete "${v.title}"? Watch history for it is removed too.`) && action.run(() => del(`/admin/videos/${v.id}`)).then(list.reload)}>Delete</Button>
                  </Td>
                </tr>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} onDone={() => { setUploadOpen(false); void list.reload(); }} />
      <Dialog open={preview !== null} onClose={() => setPreview(null)} title={preview?.title}>
        {preview && <video src={preview.url} controls className="w-full rounded-lg" />}
      </Dialog>
    </>
  );
}

function UploadDialog({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const subjects = useSubjects(classId || null);
  const [subjectId, setSubjectId] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [thumb, setThumb] = useState<File | null>(null);
  const [publish, setPublish] = useState(false);
  const [pct, setPct] = useState(0);
  const { busy, error, setError, run } = useAction();
  const chapters = subjects.data?.results.find((s) => String(s.id) === subjectId)?.chapters ?? [];

  async function submit() {
    if (!file || !chapterId || !title) return setError("Choose a chapter, a title and an MP4 file.");
    if (file.type !== "video/mp4") return setError("Only MP4 (H.264) files are supported.");
    const ok = await run(async () => {
      const duration = await readDuration(file);
      if (!duration) throw new Error("Could not read the video length. Is the file a valid MP4?");
      const r2_key = await uploadFile("videos", file, setPct);
      const thumbnail_key = thumb ? await uploadFile("thumbnails", thumb) : "";
      await post("/admin/videos", { chapter: Number(chapterId), title, description, r2_key, thumbnail_key, duration_s: duration, status: publish ? "published" : "draft" });
      return true;
    });
    if (ok) {
      setTitle("");
      setDescription("");
      setFile(null);
      setPct(0);
      onDone();
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => !busy && onClose()}
      title="Upload video"
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={submit} loading={busy}>Upload</Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Class">
            <Select value={classId} onChange={(e) => { setClassId(e.target.value); setSubjectId(""); setChapterId(""); }}>
              <option value="">—</option>
              {classes.data?.map((c) => <option key={c.id} value={c.id}>{c.grade}</option>)}
            </Select>
          </Field>
          <Field label="Subject">
            <Select value={subjectId} onChange={(e) => { setSubjectId(e.target.value); setChapterId(""); }}>
              <option value="">—</option>
              {subjects.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Chapter">
            <Select value={chapterId} onChange={(e) => setChapterId(e.target.value)}>
              <option value="">—</option>
              {chapters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
        </div>
        <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Description"><Textarea value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <Field label="Video file" hint="MP4, H.264, 720p, with the faststart flag so it streams with seeking.">
          <input type="file" accept="video/mp4" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
        <Field label="Thumbnail (optional)" hint="WebP/JPEG/PNG under 2 MB.">
          <input type="file" accept="image/webp,image/jpeg,image/png" onChange={(e) => setThumb(e.target.files?.[0] ?? null)} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={publish} onChange={(e) => setPublish(e.target.checked)} /> Publish immediately
        </label>
        {busy && <Progress value={pct} />}
        <Alert>{error}</Alert>
      </div>
    </Dialog>
  );
}
