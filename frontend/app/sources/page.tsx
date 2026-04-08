"use client";

import { useEffect, useState } from "react";
import { api, SourceHealth } from "../../lib/api";

export default function SourcesPage() {
  const [rows, setRows] = useState<SourceHealth[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .sourceHealth()
      .then((res) => setRows(res.sources))
      .catch((e) => setError(e.message ?? String(e)));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Source health</h1>
      {rows.length === 0 && (
        <p className="text-sm text-stone-500">
          No source health data yet. Run a scan first.
        </p>
      )}
      <table className="w-full text-sm">
        <thead className="text-left font-mono text-xs uppercase tracking-wider text-stone-500">
          <tr>
            <th className="py-2">Source</th>
            <th>Status</th>
            <th>Cons. fails</th>
            <th>Total runs</th>
            <th>Last error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source} className="border-t border-stone-200">
              <td className="py-2 font-mono">{r.source}</td>
              <td>
                <span
                  className={
                    r.status === "OK"
                      ? "rounded bg-radar/15 px-2 py-0.5 font-mono text-xs text-radar-dark"
                      : "rounded bg-red-100 px-2 py-0.5 font-mono text-xs text-red-700"
                  }
                >
                  {r.status}
                </span>
              </td>
              <td>{r.consecutive_failures}</td>
              <td>{r.total_runs}</td>
              <td className="max-w-md truncate text-xs text-stone-500">
                {r.last_error || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
