"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { post } from "@/lib/api";
import { useAction } from "@/lib/hooks";
import type { Me } from "@/lib/types";

function LoginForm() {
  const params = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const me = await run(() => post<Me>("/auth/login", { username: username.trim(), password }));
    if (!me) return;
    const next = params.get("next");
    const home = me.role === "admin" ? "/admin/dashboard" : "/dashboard";
    const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : home;
    // Full navigation so middleware sees the new cookies.
    window.location.href = me.must_change_password ? "/change-password" : safeNext;
  }

  return (
    <Card>
      <CardBody className="space-y-4 py-6">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Roll number">
            <Input autoComplete="username" autoCapitalize="characters" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
          </Field>
          <Field label="Password">
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <Alert>{error}</Alert>
          <Button type="submit" className="w-full" size="lg" loading={busy}>
            Log in
          </Button>
        </form>
        <p className="text-center text-xs text-muted">Forgot your password? Ask your class teacher or the school office to reset it.</p>
      </CardBody>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
