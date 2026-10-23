import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "@/lib/format";

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full text-left text-sm", className)} {...props} />
    </div>
  );
}
export const THead = (p: HTMLAttributes<HTMLTableSectionElement>) => <thead className="border-b border-border bg-subtle/60 text-xs uppercase tracking-wide text-muted" {...p} />;
export const TBody = (p: HTMLAttributes<HTMLTableSectionElement>) => <tbody className="divide-y divide-border" {...p} />;
export const Th = ({ className, ...p }: ThHTMLAttributes<HTMLTableCellElement>) => <th className={cn("px-4 py-2.5 font-medium", className)} {...p} />;
export const Td = ({ className, ...p }: TdHTMLAttributes<HTMLTableCellElement>) => <td className={cn("px-4 py-2.5 align-middle", className)} {...p} />;
