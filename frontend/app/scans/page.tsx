"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ScanRow } from "../../lib/api";

export default function ScansPage() {
  const [scans, setScans] = useState<ScanRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listScans()
      .then((res) => setScans(res.scans))
      .catch((e) => setError(e.message ?? String(e)));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Scan history</h1>
      {scans.length === 0 && (
        <p className="text-sm text-stone-500">No scans yet.</p>
      )}
      <table className="w-full text-sm">
        <thead className="text-left font-mono text-xs uppercase tracking-wider text-stone-500">
          <tr>
            <th className="py-2">#</th>
            <th>Window</th>
            <th>Status</th>
            <th>Found</th>
            <th>Scored</th>
            <th>Started</th>
          </tr>
        </thead>
        <tbody>
          {scans.map((s) => (
            <tr key={s.id} className="border-t border-stone-200">
              <td className="py-2 font-mono">
                <Link
                  href={`/scans/${s.id}`}
                  className="text-radar-dark hover:underline"
                >
                  #{s.id}
                </Link>
              </td>
              <td className="font-mono text-xs text-stone-600">
                {s.window_start.slice(0, 10)} → {s.window_end.slice(0, 10)}
              </td>
              <td>
                <span
                  className={
                    s.status === "done"
                      ? "text-radar-dark"
                      : s.status === "error"
                      ? "text-red-600"
                      : "text-amber-600"
                  }
                >
                  {s.status}
                </span>
              </td>
              <td>{s.items_found ?? "—"}</td>
              <td>{s.items_scored ?? "—"}</td>
              <td className="font-mono text-xs text-stone-500">
                {s.started_at.slice(0, 16).replace("T", " ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
