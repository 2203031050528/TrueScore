"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { ApiError, post } from "@/lib/api";
import type { Me } from "@/lib/types";

export default function ChangePasswordPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (next !== confirm) return setErrors({ confirm: "Passwords do not match." });
    setBusy(true);
    setErrors({});
    try {
      const me = await post<Me>("/auth/change-password", { current_password: current, new_password: next });
      window.location.href = me.role === "admin" ? "/admin/dashboard" : "/dashboard";
    } catch (err) {
      if (err instanceof ApiError) {
        const fields = err.fieldErrors();
        setErrors(Object.keys(fields).length ? fields : { detail: err.message });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardBody className="space-y-4 py-6">
        <div>
          <h2 className="font-semibold">Choose a new password</h2>
          <p className="text-sm text-muted">For your safety, set your own password before continuing. Use at least 8 characters.</p>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Current password" error={errors.current_password}>
            <Input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
          </Field>
          <Field label="New password" error={errors.new_password}>
            <Input type="password" autoComplete="new-password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required />
          </Field>
          <Field label="Confirm new password" error={errors.confirm}>
            <Input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </Field>
          <Alert>{errors.detail}</Alert>
          <Button type="submit" className="w-full" size="lg" loading={busy}>
            Save password
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}
