import { Shell } from "@/components/layout/shell";
import { AuthProvider } from "@/lib/auth";

const NAV = [
  { href: "/dashboard", label: "Home" },
  { href: "/videos", label: "Lessons" },
  { href: "/exams", label: "Exams" },
  { href: "/results", label: "Results" },
  { href: "/profile", label: "Profile" },
];

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <Shell nav={NAV}>{children}</Shell>
    </AuthProvider>
  );
}
