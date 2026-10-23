"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth";

export default function ProfilePage() {
  const { me } = useAuth();
  if (!me) return null;
  const p = me.profile;
  const rows: [string, string | undefined][] = [
    ["Name", me.full_name],
    ["Roll number", p?.roll_no],
    ["Class", p ? `Class ${p.grade}` : undefined],
    ["Section", p?.section_label],
    ["Academic year", p?.academic_year],
    ["Guardian contact", p?.guardian_phone || "—"],
  ];
  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title="Profile" />
      <Card>
        <CardHeader title="Your details" description="Ask the school office to correct anything that is wrong." />
        <CardBody>
          <dl className="divide-y divide-border">
            {rows.map(([k, v]) => (
              <div key={k} className="flex justify-between py-2.5 text-sm">
                <dt className="text-muted">{k}</dt>
                <dd className="font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </CardBody>
      </Card>
      <Link href="/change-password" className="mt-4 inline-block">
        <Button variant="outline">Change password</Button>
      </Link>
    </div>
  );
}
