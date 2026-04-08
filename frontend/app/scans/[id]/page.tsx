"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ScanRow, ScoredItem } from "../../../lib/api";
import ItemCard from "../../../components/ItemCard";

export default function SingleScanPage() {
  const params = useParams<{ id: string }>();
  const scanId = Number(params.id);
  const [scan, setScan] = useState<ScanRow | null>(null);
  const [items, setItems] = useState<ScoredItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getScan(scanId)
      .then((res) => {
        setScan(res.scan);
        setItems(res.items);
      })
      .catch((e) => setError(e.message ?? String(e)));
  }, [scanId]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!scan) return <p className="text-sm text-stone-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <Link href="/scans" className="text-sm text-stone-500 hover:underline">
        ← scan history
      </Link>
      <header>
        <h1 className="text-2xl font-bold">Scan #{scan.id}</h1>
        <p className="font-mono text-xs text-stone-500">
          {scan.window_start.slice(0, 16).replace("T", " ")} →{" "}
          {scan.window_end.slice(0, 16).replace("T", " ")} · status {scan.status}
        </p>
      </header>
      {items.length === 0 ? (
        <p className="text-sm text-stone-500">No scored items.</p>
      ) : (
        <div className="space-y-3">
          {items.map((item, i) => (
            <ItemCard key={item.id} item={item} rank={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
