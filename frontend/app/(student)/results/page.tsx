"use client";

import Link from "next/link";

import { ScoreTrend } from "@/components/charts/score-trend";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Alert, Badge, Empty, PageHeader, Spinner } from "@/components/ui/misc";
import { Table, TBody, Td, Th, THead } from "@/components/ui/table";
import { fmtDate, fmtNum } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ResultSummary } from "@/lib/types";

export default function ResultsPage() {
  const { data, error, loading } = useApi<ResultSummary[]>("/results");
  if (loading) return <Spinner />;
  if (error) return <Alert>{error.message}</Alert>;
  const results = data ?? [];

  return (
    <>
      <PageHeader title="Results" description="Published results only. Results you are waiting for show as Submitted on the Exams page." />
      {!results.length ? (
        <Empty title="No published results yet" />
      ) : (
        <div className="space-y-6">
          {results.length > 1 && (
            <Card>
              <CardHeader title="Score trend" />
              <CardBody>
                <ScoreTrend points={[...results].reverse().map((r) => ({ label: r.title, date: r.date, value: r.percentage }))} />
              </CardBody>
            </Card>
          )}
          <Card>
            <Table>
              <THead>
                <tr>
                  <Th>Exam</Th>
                  <Th>Date</Th>
                  <Th className="text-right">Score</Th>
                  <Th className="text-right">%</Th>
                  <Th>Result</Th>
                  <Th className="text-right">Rank</Th>
                </tr>
              </THead>
              <TBody>
                {results.map((r) => (
                  <tr key={r.exam_id} className="hover:bg-subtle">
                    <Td>
                      <Link href={`/results/${r.exam_id}`} className="font-medium text-primary">{r.title}</Link>
                      <p className="text-xs text-muted">{r.subject}</p>
                    </Td>
                    <Td>{fmtDate(r.date)}</Td>
                    <Td className="text-right tabular-nums">{fmtNum(r.score)} / {fmtNum(r.max_score)}</Td>
                    <Td className="text-right tabular-nums">{r.percentage}%</Td>
                    <Td>{r.passed ? <Badge tone="success">Pass</Badge> : <Badge tone="danger">Not passed</Badge>}</Td>
                    <Td className="text-right tabular-nums">{r.rank ? `${r.rank} / ${r.section_size}` : "—"}</Td>
                  </tr>
                ))}
              </TBody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}
