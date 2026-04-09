import Link from "next/link";
import { ScoredItem } from "../lib/api";

function scoreColor(score: number): string {
  if (score >= 9) return "text-emerald-400";
  if (score >= 7.5) return "text-lime-400";
  if (score >= 6) return "text-amber-400";
  return "text-stone-400";
}

/**
 * Rev 3.1 rubric pills. Four criteria: Usability / Innovation / Underexploited / Wow.
 *
 * Color coding follows the tech-discovery framing:
 *   Usability    → teal   (can I build with this?)
 *   Innovation   → violet (dominant ranker — most visually prominent)
 *   Underexploit → amber  (niche-ness)
 *   Wow          → rose   (tech itself provoking "wait, what?")
 */
function CriterionPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "usability" | "innovation" | "underexploited" | "wow";
}) {
  const tones: Record<string, string> = {
    usability: "bg-teal-900/60 text-teal-200 ring-1 ring-teal-500/40",
    innovation: "bg-violet-900/60 text-violet-200 ring-1 ring-violet-500/40",
    underexploited: "bg-amber-900/60 text-amber-200 ring-1 ring-amber-500/40",
    wow: "bg-rose-900/60 text-rose-200 ring-1 ring-rose-500/40",
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

function isHighConviction(item: ScoredItem): boolean {
  return (
    item.usability_score >= 7 &&
    item.innovation_score >= 9 &&
    item.underexploited_score >= 8 &&
    item.wow_score >= 7
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

  const highConviction = isHighConviction(item);

  return (
    <article
      className={`rounded-xl border ${
        highConviction
          ? "border-violet-700/60 bg-stone-950/80 shadow-violet-950/40"
          : "border-stone-800 bg-stone-950/70"
      } p-6 shadow-lg`}
    >
      {/* rank + high-conviction badge */}
      <div className="mb-2 flex items-center justify-between">
        <div className="font-mono text-xs text-stone-500">#{rank}</div>
        {highConviction && (
          <span className="rounded-full bg-violet-900/60 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-violet-200 ring-1 ring-violet-500/50">
            high conviction
          </span>
        )}
      </div>

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
            {item.total_score.toFixed(2)}
          </span>
          <span className="text-sm text-stone-500">/ 10</span>
        </div>
        <CriterionPill label="Use" value={item.usability_score ?? 0} tone="usability" />
        <CriterionPill label="Innov" value={item.innovation_score ?? 0} tone="innovation" />
        <CriterionPill
          label="Niche"
          value={item.underexploited_score ?? 0}
          tone="underexploited"
        />
        <CriterionPill label="Wow" value={item.wow_score ?? 0} tone="wow" />
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
        {item.stars !== null && item.stars !== undefined && (
          <span className="text-amber-400">
            ★ {item.stars.toLocaleString()} stars
          </span>
        )}
        {item.license && <span className="text-stone-500">{item.license}</span>}
      </div>

      {/* one-line summary (always shown) */}
      {item.summary && (
        <p className="mt-4 text-sm italic leading-relaxed text-stone-400">
          {item.summary}
        </p>
      )}

      {/* FLAGSHIP: what the tech does */}
      {item.what_the_tech_does && (
        <div className="mt-4 rounded-lg border border-stone-800/80 bg-stone-900/40 p-4">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-stone-500">
            What the tech does
          </div>
          <p className="text-sm leading-relaxed text-stone-200">
            {item.what_the_tech_does}
          </p>
        </div>
      )}

      {/* Key capabilities bullets */}
      {item.key_capabilities && item.key_capabilities.length > 0 && (
        <div className="mt-3">
          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-stone-500">
            Key capabilities
          </div>
          <ul className="space-y-1 text-sm text-stone-300">
            {item.key_capabilities.map((cap, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-violet-500">▸</span>
                <span>{cap}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Idea sparks — small italic footer, brainstorm only */}
      {item.idea_sparks && item.idea_sparks.length > 0 && (
        <div className="mt-4 border-t border-stone-800/60 pt-3">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-stone-600">
            possible directions (brainstorm)
          </div>
          <ul className="space-y-0.5 text-xs italic text-stone-500">
            {item.idea_sparks.map((spark, i) => (
              <li key={i}>· {spark}</li>
            ))}
          </ul>
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
