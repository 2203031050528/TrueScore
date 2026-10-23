import { Shell } from "@/components/layout/shell";
import { AuthProvider } from "@/lib/auth";

const NAV = [
  { href: "/admin/dashboard", label: "Dashboard" },
  { href: "/admin/students", label: "Students" },
  { href: "/admin/classes", label: "Classes" },
  { href: "/admin/videos", label: "Videos" },
  { href: "/admin/questions", label: "Questions" },
  { href: "/admin/exams", label: "Exams" },
  { href: "/admin/audit", label: "Audit log" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Shell nav={NAV} wide>
        {children}
      </Shell>
    </AuthProvider>
  );
}
