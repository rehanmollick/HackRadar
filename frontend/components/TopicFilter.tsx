"use client";

import { Topic, TOPIC_LABELS } from "../lib/topics";

/**
 * Chip row for toggling topic visibility.
 *
 * Behavior: all topics start ENABLED (visible). Clicking a chip toggles
 * it OFF — the items in that bucket are hidden from the list. Clicking
 * again toggles it back on. "All" resets to the enabled set.
 *
 * This is the "if the top 5 are all 3DGS, hide 3D so I can see what's
 * below" use case. The pipeline still ranks all items as-is; the UI
 * just slices the view.
 */
export default function TopicFilter({
  buckets,
  disabled,
  onToggle,
  onReset,
}: {
  buckets: Array<{ topic: Topic; count: number }>;
  disabled: Set<Topic>;
  onToggle: (topic: Topic) => void;
  onReset: () => void;
}) {
  if (buckets.length <= 1) return null;

  const anyDisabled = disabled.size > 0;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={onReset}
        disabled={!anyDisabled}
        className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 transition ${
          anyDisabled
            ? "bg-stone-800 text-stone-200 ring-stone-600 hover:bg-stone-700"
            : "bg-stone-900/60 text-stone-500 ring-stone-800"
        }`}
        title="Show all topics"
      >
        All
      </button>
      {buckets.map(({ topic, count }) => {
        const off = disabled.has(topic);
        return (
          <button
            key={topic}
            type="button"
            onClick={() => onToggle(topic)}
            className={`rounded-full px-3 py-1 text-xs font-medium ring-1 transition ${
              off
                ? "bg-stone-900/40 text-stone-600 ring-stone-800 line-through decoration-stone-700"
                : "bg-stone-800 text-stone-200 ring-stone-600 hover:bg-stone-700"
            }`}
            title={off ? `Show ${TOPIC_LABELS[topic]}` : `Hide ${TOPIC_LABELS[topic]}`}
          >
            {TOPIC_LABELS[topic]}
            <span className="ml-1 font-mono text-[10px] text-stone-500">{count}</span>
          </button>
        );
      })}
    </div>
  );
}
