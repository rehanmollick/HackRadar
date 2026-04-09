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
      <body className="min-h-screen bg-stone-950 text-stone-200">
        <header className="border-b border-stone-800 bg-stone-950/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2">
              <span className="text-2xl">🛰️</span>
              <span className="font-mono text-lg font-bold text-stone-100">hackradar</span>
              <span className="text-xs font-mono text-stone-500">v2</span>
            </Link>
            <nav className="flex items-center gap-4 text-sm text-stone-400">
              <Link href="/" className="hover:text-stone-100">
                Latest scan
              </Link>
              <Link href="/scans" className="hover:text-stone-100">
                Scan history
              </Link>
              <Link href="/sources" className="hover:text-stone-100">
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
