import Link from "next/link";
import { ScoredItem, scoreClass } from "../lib/api";

export default function ItemCard({ item, rank }: { item: ScoredItem; rank: number }) {
  const links: Array<[string, string | null]> = [
    ["paper", item.paper_url],
    ["code", item.github_url],
    ["model", item.huggingface_url],
    ["demo", item.demo_url],
    ["source", item.source_url],
  ];
  return (
    <article className="rounded-lg border border-stone-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2 text-xs text-stone-500">
            <span className="font-mono font-bold">#{rank}</span>
            <span>·</span>
            <span>{item.source}</span>
            {item.all_sources?.length > 1 && (
              <span className="text-stone-400">
                +{item.all_sources.length - 1} more source
                {item.all_sources.length > 2 ? "s" : ""}
              </span>
            )}
            {item.category && (
              <>
                <span>·</span>
                <span>{item.category}</span>
              </>
            )}
            {item.stars !== null && (
              <>
                <span>·</span>
                <span>★ {item.stars.toLocaleString()}</span>
              </>
            )}
          </div>
          <h2 className="text-lg font-bold leading-tight">
            <Link href={`/items/${item.id}`} className="hover:underline">
              {item.title}
            </Link>
          </h2>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className={scoreClass(item.total_score)}>
            {item.total_score.toFixed(2)}
          </span>
          <div className="flex gap-1 font-mono text-[10px] text-stone-500">
            <span title="Open">O{item.open_score.toFixed(0)}</span>
            <span title="Novelty">N{item.novelty_score.toFixed(0)}</span>
            <span title="Wow">W{item.wow_score.toFixed(0)}</span>
            <span title="Build">B{item.build_score.toFixed(0)}</span>
          </div>
        </div>
      </div>

      {item.summary && (
        <p className="mt-3 text-sm text-stone-700">{item.summary}</p>
      )}
      {item.hackathon_idea && (
        <div className="mt-3 rounded-md border-l-4 border-radar bg-radar/5 px-3 py-2 text-sm">
          <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-radar-dark">
            hackathon idea
          </span>
          <p className="mt-1 text-stone-800">{item.hackathon_idea}</p>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {links
          .filter(([, url]) => !!url)
          .map(([label, url]) => (
            <a
              key={label}
              href={url!}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-stone-300 px-2 py-0.5 font-mono text-stone-600 hover:border-stone-500 hover:text-stone-900"
            >
              {label} ↗
            </a>
          ))}
      </div>
    </article>
  );
}
