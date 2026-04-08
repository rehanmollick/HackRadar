import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "HackRadar",
  description: "Hackathon technology discovery for builders.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-stone-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl">🛰️</span>
              <span className="font-mono text-lg font-bold">hackradar</span>
              <span className="text-xs font-mono text-stone-500">v2</span>
            </Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link href="/" className="hover:underline">
                Latest scan
              </Link>
              <Link href="/scans" className="hover:underline">
                Scan history
              </Link>
              <Link href="/sources" className="hover:underline">
                Source health
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
