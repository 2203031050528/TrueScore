"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { useClasses, useSubjects } from "@/lib/admin";
import { ApiError, api, uploadFile } from "@/lib/api";
import type { Difficulty, Question, QuestionOption, QuestionType } from "@/lib/types";

const TYPES: { value: QuestionType; label: string }[] = [
  { value: "mcq_single", label: "MCQ — one answer" },
  { value: "mcq_multi", label: "MCQ — multiple answers" },
  { value: "true_false", label: "True / False" },
  { value: "numeric", label: "Numeric" },
  { value: "short_answer", label: "Short answer (marked by hand)" },
];

const blankOptions = (): QuestionOption[] => [0, 1, 2, 3].map(() => ({ text: "", is_correct: false }));

export function QuestionEditor({ open, question, onClose, onSaved }: { open: boolean; question: Question | null; onClose: () => void; onSaved: (msg?: string) => void }) {
  const classes = useClasses();
  const [classId, setClassId] = useState("");
  const subjects = useSubjects(classId || null);
  const [subject, setSubject] = useState("");
  const [chapter, setChapter] = useState("");
  const [type, setType] = useState<QuestionType>("mcq_single");
  const [text, setText] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [marks, setMarks] = useState("1");
  const [negative, setNegative] = useState("0");
  const [explanation, setExplanation] = useState("");
  const [numeric, setNumeric] = useState("");
  const [tolerance, setTolerance] = useState("0");
  const [options, setOptions] = useState<QuestionOption[]>(blankOptions());
  const [imageKey, setImageKey] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const q = question;
    setClassId(q ? String(classes.data?.find((c) => c.grade === q.grade)?.id ?? "") : "");
    setSubject(q ? String(q.subject) : "");
    setChapter(q ? String(q.chapter) : "");
    setType(q?.type ?? "mcq_single");
    setText(q?.text ?? "");
    setDifficulty(q?.difficulty ?? "medium");
    setMarks(q?.marks ?? "1");
    setNegative(q?.negative_marks ?? "0");
    setExplanation(q?.explanation ?? "");
    setNumeric(q?.numeric_answer ?? "");
    setTolerance(q?.numeric_tolerance ?? "0");
    setOptions(q?.options.length ? q.options.map((o) => ({ text: o.text, is_correct: o.is_correct })) : blankOptions());
    setImageKey(q?.image_key ?? "");
    setErrors({});
  }, [open, question, classes.data]);

  useEffect(() => {
    if (type === "true_false" && (options.length !== 2 || options[0].text !== "True")) {
      setOptions([{ text: "True", is_correct: true }, { text: "False", is_correct: false }]);
    }
  }, [type]); // eslint-disable-line react-hooks/exhaustive-deps

  const chapters = subjects.data?.results.find((s) => String(s.id) === subject)?.chapters ?? [];
  const hasOptions = type === "mcq_single" || type === "mcq_multi" || type === "true_false";

  function setCorrect(i: number, on: boolean) {
    setOptions(options.map((o, j) => ({ ...o, is_correct: type === "mcq_multi" ? (j === i ? on : o.is_correct) : j === i })));
  }

  async function save() {
    setBusy(true);
    setErrors({});
    const body: Record<string, unknown> = {
      subject: Number(subject), chapter: Number(chapter), type, text, difficulty, marks, negative_marks: negative, explanation, image_key: imageKey,
      options: hasOptions ? options.filter((o) => o.text.trim()).map((o, i) => ({ ...o, order: i })) : [],
      numeric_answer: type === "numeric" ? numeric || null : null,
      numeric_tolerance: type === "numeric" ? tolerance || "0" : "0",
    };
    try {
      const res = await api<Question & { versioned_from?: number }>(question ? `/admin/questions/${question.id}` : "/admin/questions", { method: question ? "PUT" : "POST", body });
      onSaved(res.versioned_from ? `This question is used in a scheduled exam, so version ${res.version} was created. The exam keeps the original.` : undefined);
    } catch (e) {
      if (e instanceof ApiError) setErrors({ detail: e.message, ...e.fieldErrors() });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={question ? `Edit question #${question.id}` : "New question"}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={save} loading={busy}>Save</Button>
        </>
      }
    >
      <div className="space-y-4">
        {question?.locked && <Alert tone="warning">Used in a scheduled exam — saving creates a new version.</Alert>}
        <div className="grid grid-cols-3 gap-3">
          <Field label="Class">
            <Select value={classId} onChange={(e) => { setClassId(e.target.value); setSubject(""); setChapter(""); }}>
              <option value="">—</option>
              {classes.data?.map((c) => <option key={c.id} value={c.id}>{c.grade}</option>)}
            </Select>
          </Field>
          <Field label="Subject" error={errors.subject}>
            <Select value={subject} onChange={(e) => { setSubject(e.target.value); setChapter(""); }}>
              <option value="">—</option>
              {subjects.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </Select>
          </Field>
          <Field label="Chapter" error={errors.chapter}>
            <Select value={chapter} onChange={(e) => setChapter(e.target.value)}>
              <option value="">—</option>
              {chapters.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <Select value={type} onChange={(e) => setType(e.target.value as QuestionType)}>
              {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
          </Field>
          <Field label="Difficulty">
            <Select value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)}>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </Select>
          </Field>
        </div>
        <Field label="Question" error={errors.text}><Textarea value={text} onChange={(e) => setText(e.target.value)} /></Field>
        <Field label="Image (optional)" hint={imageKey ? "Image attached." : "WebP/JPEG/PNG, under 200 KB recommended."}>
          <input type="file" accept="image/webp,image/jpeg,image/png" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setImageKey(await uploadFile("questions", f)); }} />
        </Field>
        {hasOptions && (
          <Field label={type === "mcq_multi" ? "Options (tick every correct one)" : "Options (tick the correct one)"} error={errors.options}>
            <div className="space-y-2">
              {options.map((o, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    type={type === "mcq_multi" ? "checkbox" : "radio"}
                    name="correct"
                    checked={o.is_correct}
                    onChange={(e) => setCorrect(i, e.target.checked)}
                    aria-label={`Option ${i + 1} is correct`}
                  />
                  <Input value={o.text} disabled={type === "true_false"} onChange={(e) => setOptions(options.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} placeholder={`Option ${i + 1}`} />
                  {type !== "true_false" && options.length > 2 && (
                    <button className="text-muted hover:text-danger" onClick={() => setOptions(options.filter((_, j) => j !== i))} aria-label="Remove option">×</button>
                  )}
                </div>
              ))}
              {type !== "true_false" && options.length < 8 && (
                <Button size="sm" variant="ghost" onClick={() => setOptions([...options, { text: "", is_correct: false }])}>+ Add option</Button>
              )}
            </div>
          </Field>
        )}
        {type === "numeric" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Correct value" error={errors.numeric_answer}><Input value={numeric} onChange={(e) => setNumeric(e.target.value)} /></Field>
            <Field label="Tolerance (±)"><Input value={tolerance} onChange={(e) => setTolerance(e.target.value)} /></Field>
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Marks" error={errors.marks}><Input value={marks} onChange={(e) => setMarks(e.target.value)} /></Field>
          <Field label="Negative marks" error={errors.negative_marks}><Input value={negative} onChange={(e) => setNegative(e.target.value)} /></Field>
        </div>
        <Field label="Explanation" hint="Shown to students after results are published."><Textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} /></Field>
        <Alert>{Object.keys(errors).length === 1 ? errors.detail : errors.non_field_errors}</Alert>
      </div>
    </Dialog>
  );
}
