"use client";

import { useRouter } from "next/navigation";

import { ExamDetailsForm } from "@/components/admin/exam-details-form";
import { Card, CardBody } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/misc";

export default function NewExamPage() {
  const router = useRouter();
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="New exam" description="Next you will add parts and questions, then schedule it." />
      <Card>
        <CardBody>
          <ExamDetailsForm onSaved={(e) => router.push(`/admin/exams/${e.id}/edit`)} />
        </CardBody>
      </Card>
    </div>
  );
}
