"use client";

import { useState } from "react";
import { api } from "../lib/api";

export default function ScanTrigger({ onStarted }: { onStarted?: (id: number) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [enrich, setEnrich] = useState(true);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { enrich };
      if (from && to) {
        body.from_date = from;
        body.to_date = to;
      }
      const res = await api.startScan(body);
      onStarted?.(res.scan_id);
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-mono text-sm font-bold uppercase tracking-wider text-stone-500">
          Run a scan
        </h3>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs">
          <span className="mb-1 text-stone-500">From</span>
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="rounded-md border border-stone-300 px-2 py-1 font-mono text-sm"
          />
        </label>
        <label className="flex flex-col text-xs">
          <span className="mb-1 text-stone-500">To</span>
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="rounded-md border border-stone-300 px-2 py-1 font-mono text-sm"
          />
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={enrich}
            onChange={(e) => setEnrich(e.target.checked)}
          />
          Enrich
        </label>
        <button onClick={start} disabled={busy} className="btn btn-primary">
          {busy ? "Starting…" : "Scan"}
        </button>
      </div>
      {(!from || !to) && !busy && (
        <p className="mt-2 text-xs text-stone-500">
          Leave blank to scan the last 48 hours.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
