import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "TrueScore", template: "%s · TrueScore" },
  description: "Lessons, progress and secure exams for classes 1–12.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
