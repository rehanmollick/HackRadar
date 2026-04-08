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
            O{item.open_score.toFixed(0)} N{item.novelty_score.toFixed(0)} W
            {item.wow_score.toFixed(0)} B{item.build_score.toFixed(0)}
          </span>
        </div>
        <h1 className="text-3xl font-bold leading-tight">{item.title}</h1>
        <p className="mt-1 font-mono text-xs text-stone-500">
          {item.source} · {item.category} ·{" "}
          {item.date.slice(0, 10)}
          {item.stars !== null && ` · ★ ${item.stars.toLocaleString()}`}
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
            Pass 2 summary
          </h3>
          <p className="text-stone-800">{item.summary}</p>
          {item.hackathon_idea && (
            <div className="mt-4 rounded-md border-l-4 border-radar bg-radar/5 px-3 py-2">
              <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-radar-dark">
                hackathon idea
              </span>
              <p className="mt-1 text-stone-800">{item.hackathon_idea}</p>
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
