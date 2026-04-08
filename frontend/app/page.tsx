"use client";

import { useEffect, useState } from "react";
import { api, ScanRow, ScoredItem } from "../lib/api";
import ScanTrigger from "../components/ScanTrigger";
import ItemCard from "../components/ItemCard";

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
            <span className="font-mono text-xs uppercase text-stone-500">
              {scan.status}
            </span>
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
