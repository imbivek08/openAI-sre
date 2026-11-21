import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "OpenSRE AI",
  description: "Open-source AI Site Reliability Engineering agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <nav className="border-b border-neutral-800 bg-neutral-950 px-6 py-3 flex items-center gap-6">
          <Link href="/" className="text-lg font-bold text-white">
            OpenSRE AI
          </Link>
          <Link href="/" className="text-sm text-neutral-400 hover:text-white">
            Overview
          </Link>
          <Link href="/demo" className="text-sm text-neutral-400 hover:text-white">
            Demo Lab
          </Link>
          <Link href="/settings" className="text-sm text-neutral-400 hover:text-white">
            Settings
          </Link>
        </nav>
        <main className="mx-auto max-w-7xl p-6">{children}</main>
      </body>
    </html>
  );
}
