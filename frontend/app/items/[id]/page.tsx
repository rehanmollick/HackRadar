"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, ChatRow, ScoredItem, scoreClass } from "../../../lib/api";
import ChatPanel from "../../../components/ChatPanel";

export default function ItemDetailPage() {
  const params = useParams<{ id: string }>();
  const itemId = Number(params.id);
  const [item, setItem] = useState<ScoredItem | null>(null);
  const [chats, setChats] = useState<ChatRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getItem(itemId)
      .then((res) => {
        if (cancelled) return;
        setItem(res.item);
        setChats(res.chats);
      })
      .catch((e) => setError(e.message ?? String(e)));
    return () => {
      cancelled = true;
    };
  }, [itemId]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!item) return <p className="text-sm text-stone-500">Loading…</p>;

  return (
    <div className="space-y-6">
      <Link href="/" className="text-sm text-stone-500 hover:underline">
        ← back to latest scan
      </Link>

      <header>
        <div className="mb-2 flex items-center gap-3">
          <span className={scoreClass(item.total_score)}>
            {item.total_score.toFixed(2)}
          </span>
          <span className="font-mono text-xs text-stone-500">
            U{(item.usability_score ?? 0).toFixed(0)} I
            {(item.innovation_score ?? 0).toFixed(0)} Un
            {(item.underexploited_score ?? 0).toFixed(0)} W
            {(item.wow_score ?? 0).toFixed(0)}
          </span>
        </div>
        <h1 className="text-3xl font-bold leading-tight">{item.title}</h1>
        <p className="mt-1 font-mono text-xs text-stone-500">
          {item.source} · {item.category} ·{" "}
          {item.date.slice(0, 10)}
          {item.stars !== null && item.stars !== undefined && ` · ★ ${item.stars.toLocaleString()}`}
          {item.language && ` · ${item.language}`}
        </p>
      </header>

      {item.description && (
        <p className="text-base leading-relaxed text-stone-800">
          {item.description}
        </p>
      )}

      {item.summary && (
        <section className="rounded-lg border border-stone-200 bg-white p-5">
          <h3 className="mb-2 font-mono text-sm font-bold uppercase tracking-wider text-stone-500">
            Summary
          </h3>
          <p className="italic text-stone-700">{item.summary}</p>

          {item.what_the_tech_does && (
            <div className="mt-4">
              <h4 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-wider text-stone-500">
                What the tech does
              </h4>
              <p className="leading-relaxed text-stone-800">
                {item.what_the_tech_does}
              </p>
            </div>
          )}

          {item.key_capabilities && item.key_capabilities.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-wider text-stone-500">
                Key capabilities
              </h4>
              <ul className="space-y-1 text-sm text-stone-800">
                {item.key_capabilities.map((cap, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-radar-dark">▸</span>
                    <span>{cap}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {item.idea_sparks && item.idea_sparks.length > 0 && (
            <div className="mt-4 border-t border-stone-200 pt-3">
              <h4 className="mb-1 font-mono text-[11px] font-bold uppercase tracking-wider text-stone-500">
                possible directions (brainstorm)
              </h4>
              <ul className="space-y-0.5 text-xs italic text-stone-600">
                {item.idea_sparks.map((spark, i) => (
                  <li key={i}>· {spark}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h3 className="mb-3 font-mono text-sm font-bold uppercase tracking-wider text-stone-500">
          Links
        </h3>
        <ul className="space-y-1 text-sm">
          {item.source_url && (
            <li>
              <a
                href={item.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-radar-dark hover:underline"
              >
                source ↗
              </a>
            </li>
          )}
          {item.github_url && (
            <li>
              <a
                href={item.github_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-radar-dark hover:underline"
              >
                github ↗
              </a>
            </li>
          )}
          {item.huggingface_url && (
            <li>
              <a
                href={item.huggingface_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-radar-dark hover:underline"
              >
                huggingface ↗
              </a>
            </li>
          )}
          {item.paper_url && (
            <li>
              <a
                href={item.paper_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-radar-dark hover:underline"
              >
                paper ↗
              </a>
            </li>
          )}
          {item.demo_url && (
            <li>
              <a
                href={item.demo_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-radar-dark hover:underline"
              >
                demo ↗
              </a>
            </li>
          )}
        </ul>
      </section>

      <ChatPanel itemId={item.id} initialChats={chats} />
    </div>
  );
}
