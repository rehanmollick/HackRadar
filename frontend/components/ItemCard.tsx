import Link from "next/link";
import { ScoredItem } from "../lib/api";

function scoreColor(score: number): string {
  if (score >= 9) return "text-emerald-400";
  if (score >= 7.5) return "text-lime-400";
  if (score >= 6) return "text-amber-400";
  return "text-stone-400";
}

function CriterionPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "open" | "novel" | "wow" | "build";
}) {
  const tones: Record<string, string> = {
    open: "bg-sky-900/60 text-sky-200 ring-1 ring-sky-500/40",
    novel: "bg-violet-900/60 text-violet-200 ring-1 ring-violet-500/40",
    wow: "bg-amber-900/60 text-amber-200 ring-1 ring-amber-500/40",
    build: "bg-teal-900/60 text-teal-200 ring-1 ring-teal-500/40",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${tones[tone]}`}
    >
      <span>{label}</span>
      <span className="font-mono">{value.toFixed(0)}</span>
    </span>
  );
}

export default function ItemCard({
  item,
  rank,
}: {
  item: ScoredItem;
  rank: number;
}) {
  const sourceCount = item.all_sources?.length || 1;
  const sourceList =
    item.all_sources && item.all_sources.length > 0
      ? item.all_sources.join(", ")
      : item.source;

  const detailLinks: Array<[string, string, string | null]> = [
    ["Paper", "text-sky-400 hover:text-sky-300", item.paper_url],
    ["Code", "text-emerald-400 hover:text-emerald-300", item.github_url],
    ["Model", "text-violet-400 hover:text-violet-300", item.huggingface_url],
    ["Demo", "text-amber-400 hover:text-amber-300", item.demo_url],
    ["Source", "text-stone-400 hover:text-stone-200", item.source_url],
  ];

  return (
    <article className="rounded-xl border border-stone-800 bg-stone-950/70 p-6 shadow-lg">
      {/* rank */}
      <div className="mb-2 font-mono text-xs text-stone-500">#{rank}</div>

      {/* title */}
      <h2 className="text-xl font-bold leading-snug text-stone-50">
        <Link href={`/items/${item.id}`} className="hover:underline">
          {item.title}
        </Link>
      </h2>

      {/* score row */}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <div className="flex items-baseline gap-1">
          <span className={`text-3xl font-bold ${scoreColor(item.total_score)}`}>
            {item.total_score.toFixed(1)}
          </span>
          <span className="text-sm text-stone-500">/ 10</span>
        </div>
        <CriterionPill label="Open" value={item.open_score} tone="open" />
        <CriterionPill label="Novel" value={item.novelty_score} tone="novel" />
        <CriterionPill label="Wow" value={item.wow_score} tone="wow" />
        <CriterionPill label="Build" value={item.build_score} tone="build" />
      </div>

      {/* meta row */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500">
        <span>
          Found on{" "}
          <span className="font-semibold text-stone-300">
            {sourceCount} source{sourceCount > 1 ? "s" : ""}
          </span>
          <span className="mx-2">·</span>
          <span className="text-stone-400">{sourceList}</span>
        </span>
        {item.stars !== null && (
          <span className="text-amber-400">
            ★ {item.stars.toLocaleString()} stars
          </span>
        )}
        {item.license && <span className="text-stone-500">{item.license}</span>}
      </div>

      {/* description */}
      {item.summary && (
        <p className="mt-4 text-sm leading-relaxed text-stone-300">
          {item.summary}
        </p>
      )}

      {/* hackathon idea callout */}
      {item.hackathon_idea && (
        <div className="mt-4 rounded-lg border-l-4 border-amber-500 bg-amber-950/30 p-4">
          <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
            <span>💡</span>
            <span>Hackathon idea</span>
          </div>
          <p className="text-sm leading-relaxed text-stone-200">
            {item.hackathon_idea}
          </p>
        </div>
      )}

      {/* stack / why now / effort */}
      {(item.tech_stack || item.why_now || item.effort_estimate) && (
        <div className="mt-4 space-y-2 text-sm">
          {item.tech_stack && (
            <div>
              <span className="font-semibold text-stone-400">Stack: </span>
              <span className="text-stone-300">{item.tech_stack}</span>
            </div>
          )}
          {item.why_now && (
            <div>
              <span className="font-semibold text-stone-400">Why now: </span>
              <span className="text-stone-300">{item.why_now}</span>
            </div>
          )}
          {item.effort_estimate && (
            <div>
              <span className="font-semibold text-stone-400">Effort: </span>
              <span className="text-stone-300">{item.effort_estimate}</span>
            </div>
          )}
        </div>
      )}

      {/* links */}
      <div className="mt-5 flex flex-wrap gap-4 border-t border-stone-800 pt-4 text-sm font-medium">
        {detailLinks
          .filter(([, , url]) => !!url)
          .map(([label, className, url]) => (
            <a
              key={label}
              href={url!}
              target="_blank"
              rel="noopener noreferrer"
              className={`${className} transition-colors`}
            >
              {label}
            </a>
          ))}
      </div>
    </article>
  );
}
