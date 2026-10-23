import { NextResponse, type NextRequest } from "next/server";

// Routing only. `ts_role` is a hint set by Django next to the httpOnly JWT cookies; it grants nothing —
// every API call is authorised by Django, so tampering with it only shows an empty page.
const ROLE_COOKIE = "ts_role";
const STUDENT_PREFIXES = ["/dashboard", "/videos", "/exams", "/results", "/profile"];

function readRole(req: NextRequest): { role: string; mustChange: boolean } | null {
  const raw = req.cookies.get(ROLE_COOKIE)?.value;
  if (!raw) return null;
  const [role, flag] = decodeURIComponent(raw).replace(/"/g, "").split(":");
  return role ? { role, mustChange: flag === "1" } : null;
}

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  const session = readRole(req);
  const home = session?.role === "admin" ? "/admin/dashboard" : "/dashboard";
  const redirect = (to: string) => NextResponse.redirect(new URL(to, req.url));

  if (pathname === "/" || pathname === "/login") {
    return session ? redirect(session.mustChange ? "/change-password" : home) : pathname === "/" ? redirect("/login") : NextResponse.next();
  }
  if (!session) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  if (session.mustChange && pathname !== "/change-password") return redirect("/change-password");
  if (pathname.startsWith("/admin") && session.role !== "admin") return redirect(home);
  if (STUDENT_PREFIXES.some((p) => pathname.startsWith(p)) && session.role !== "student") return redirect(home);
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
