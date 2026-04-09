"use client";

import { useEffect, useState } from "react";
import { api, ScanRow, ScoredItem } from "../lib/api";
import ScanTrigger from "../components/ScanTrigger";
import ItemCard from "../components/ItemCard";

/**
 * Render a scan as LLM-optimized Markdown.
 *
 * Why Markdown and not PDF/JSON:
 *   - PDFs waste tokens on layout metadata (fonts, positions, etc.)
 *   - JSON wastes tokens on {}, "", and escaping
 *   - Markdown is what LLMs natively parse best — zero ambiguity
 *
 * Structure is denormalized-by-item so an LLM can answer questions about a
 * single item without cross-referencing. The front-matter-ish header tells the
 * model what the rubric means so it doesn't have to guess.
 */
function formatScanAsMarkdown(scan: ScanRow, items: ScoredItem[]): string {
  const L: string[] = [];
  L.push(`# HackRadar Scan #${scan.id}`);
  L.push("");
  L.push(`Window: ${scan.window_start.slice(0, 10)} → ${scan.window_end.slice(0, 10)}`);
  L.push(`Items scored: ${items.length} (from ${scan.items_found ?? 0} raw candidates)`);
  L.push(`Generated: ${new Date().toISOString().slice(0, 19)}Z`);
  L.push("");
  L.push("## About this document");
  L.push("");
  L.push(
    "This is a ranked list of newly-released open-source technology (models, tools, libraries, research) scored for hackathon building potential. Each item is evaluated by the rev 3.1 tech-discovery rubric:",
  );
  L.push("");
  L.push("- **Usability (30%)** — how buildable is the artifact right now? Code+weights+demo = 10, paper-only = 2.");
  L.push("- **Innovation (35%)** — how technically novel is the idea? This is the dominant ranker.");
  L.push("- **Underexploited (25%)** — how few products have been built on it? Recency + adoption.");
  L.push("- **Wow (10%)** — does the tech itself provoke a 'wait, what?' reaction?");
  L.push("");
  L.push("Items are sorted by weighted total score. The hacker is a CS student with React/Next.js/Python/TypeScript experience, free T4 GPU access, Claude Code, and willingness to spend days on complex setup. Assume aggressive buildability.");
  L.push("");
  L.push("---");
  L.push("");

  items.forEach((it, i) => {
    const rank = i + 1;
    const u = (it.usability_score ?? 0).toFixed(0);
    const inn = (it.innovation_score ?? 0).toFixed(0);
    const un = (it.underexploited_score ?? 0).toFixed(0);
    const w = (it.wow_score ?? 0).toFixed(0);

    L.push(`## #${rank}. ${it.title} — ${it.total_score.toFixed(2)}`);
    L.push("");
    L.push(`- Scores: Usability=${u}, Innovation=${inn}, Underexploited=${un}, Wow=${w}`);

    const extraSources = (it.all_sources || []).filter((s) => s !== it.source);
    const sourceLine = extraSources.length > 0
      ? `${it.source} (also seen on: ${extraSources.join(", ")})`
      : it.source;
    L.push(`- Source: ${sourceLine}`);
    L.push(`- Category: ${it.category ?? "unknown"}`);
    L.push(`- Published: ${it.date.slice(0, 10)}`);
    if (it.stars != null) L.push(`- GitHub stars: ${it.stars.toLocaleString()}`);
    if (it.language) L.push(`- Primary language: ${it.language}`);
    if (it.license) L.push(`- License: ${it.license}`);
    L.push("");

    const links: Array<[string, string | null | undefined]> = [
      ["GitHub", it.github_url],
      ["HuggingFace", it.huggingface_url],
      ["Paper", it.paper_url],
      ["Demo", it.demo_url],
      ["Source URL", it.source_url],
    ];
    const real = links.filter(([, u2]) => !!u2);
    if (real.length > 0) {
      L.push("**Links:**");
      real.forEach(([label, url]) => L.push(`- ${label}: ${url}`));
      L.push("");
    }

    if (it.summary) {
      L.push("**Summary:**");
      L.push(it.summary);
      L.push("");
    }

    if (it.what_the_tech_does) {
      L.push("**What the tech does:**");
      L.push(it.what_the_tech_does);
      L.push("");
    }

    if (it.key_capabilities && it.key_capabilities.length > 0) {
      L.push("**Key capabilities:**");
      it.key_capabilities.forEach((c) => L.push(`- ${c}`));
      L.push("");
    }

    if (it.idea_sparks && it.idea_sparks.length > 0) {
      L.push("**Brainstorm directions:**");
      it.idea_sparks.forEach((s) => L.push(`- ${s}`));
      L.push("");
    }

    L.push("---");
    L.push("");
  });

  return L.join("\n");
}

function downloadScanMarkdown(scan: ScanRow, items: ScoredItem[]) {
  const md = formatScanAsMarkdown(scan, items);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `hackradar-scan-${scan.id}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function HomePage() {
  const [scan, setScan] = useState<ScanRow | null>(null);
  const [items, setItems] = useState<ScoredItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollScanId, setPollScanId] = useState<number | null>(null);

  async function loadLatest() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.latestScan();
      setScan(res.scan);
      setItems(res.items);
    } catch (e: any) {
      if (String(e.message).startsWith("404")) {
        setScan(null);
        setItems([]);
      } else {
        setError(e.message ?? String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadLatest();
  }, []);

  // Poll a fresh in-flight scan until it finishes, then refresh.
  useEffect(() => {
    if (pollScanId === null) return;
    const tick = async () => {
      try {
        const res = await api.getScan(pollScanId);
        if (res.scan.status !== "running") {
          setPollScanId(null);
          await loadLatest();
        }
      } catch {
        // ignore transient errors
      }
    };
    const id = setInterval(tick, 2000);
    return () => clearInterval(id);
  }, [pollScanId]);

  return (
    <div className="space-y-6">
      <ScanTrigger onStarted={(id) => setPollScanId(id)} />

      {pollScanId !== null && (
        <div className="rounded-md border border-radar/30 bg-radar/5 px-4 py-3 text-sm">
          <span className="font-mono">Scan #{pollScanId}</span> is running…
          polling every 2s. This usually takes 30s–2min depending on source count.
        </div>
      )}

      {loading && <p className="text-sm text-stone-500">Loading latest scan…</p>}
      {error && <p className="text-sm text-red-600">Error: {error}</p>}

      {scan && (
        <section>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold">Latest scan #{scan.id}</h1>
              <p className="font-mono text-xs text-stone-500">
                {scan.window_start.slice(0, 16).replace("T", " ")} →{" "}
                {scan.window_end.slice(0, 16).replace("T", " ")} ·{" "}
                {scan.items_scored ?? 0} items scored from {scan.items_found ?? 0}{" "}
                raw
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => downloadScanMarkdown(scan, items)}
                disabled={items.length === 0}
                className="rounded-md border border-violet-500/50 bg-violet-900/40 px-3 py-1.5 text-xs font-semibold text-violet-200 ring-1 ring-violet-500/30 transition hover:bg-violet-800/60 hover:text-violet-100 disabled:cursor-not-allowed disabled:opacity-40"
                title="Download as LLM-optimized Markdown"
              >
                ↓ Export for LLM
              </button>
              <span className="font-mono text-xs uppercase text-stone-500">
                {scan.status}
              </span>
            </div>
          </div>
          {items.length === 0 ? (
            <p className="text-sm text-stone-500">No scored items in this scan.</p>
          ) : (
            <div className="space-y-3">
              {items.map((item, i) => (
                <ItemCard key={item.id} item={item} rank={i + 1} />
              ))}
            </div>
          )}
        </section>
      )}

      {!loading && !scan && (
        <div className="rounded-md border border-stone-200 bg-white p-6 text-center">
          <p className="text-sm text-stone-600">
            No scans yet. Trigger one above to see ranked finds.
          </p>
        </div>
      )}
    </div>
  );
}
