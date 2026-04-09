/**
 * Topic inference for filter chips.
 *
 * Why client-side: these are presentation filters only. The pipeline
 * ranks and scores; the UI lets the user slice the result. Zero cost,
 * no round-trip, no pipeline churn. If the top 5 items are all gaussian
 * splatting, that's real signal about where the bleeding edge is — the
 * user toggles the 3D chip off to see what's below, then toggles it back
 * on when they want to dive into the cluster.
 *
 * Each item maps to EXACTLY ONE topic via the first keyword hit in the
 * priority order below. Ordering matters: bio/robotics are more specific
 * than vision and must be checked first, or a "brain activity prediction
 * foundation model" would get bucketed as vision just because it happens
 * to mention "image" in its description.
 */
import type { ScoredItem } from "./api";

export type Topic =
  | "bio"
  | "robotics"
  | "3d"
  | "video"
  | "audio"
  | "vision"
  | "agent"
  | "llm"
  | "browser"
  | "dataset"
  | "tool"
  | "other";

export const TOPIC_LABELS: Record<Topic, string> = {
  bio: "Bio / Neuro",
  robotics: "Robotics",
  "3d": "3D / Graphics",
  video: "Video",
  audio: "Audio / Speech",
  vision: "Vision",
  agent: "Agents",
  llm: "LLM / NLP",
  browser: "Web / Browser",
  dataset: "Datasets",
  tool: "Dev Tools",
  other: "Other",
};

/**
 * Ordered list of (topic, regex) rules. First match wins per item.
 * The regexes are applied against a concatenation of title + summary +
 * what_the_tech_does so both the name AND the explainer feed the decision.
 */
const RULES: Array<[Topic, RegExp]> = [
  // Bio / Neuro / Chem — most specific, needs to beat vision.
  [
    "bio",
    /\b(brain|neural activity|neuroscien|fmri|eeg|protein|molecul|drug discovery|medical imaging|genom|bioinformat|biology|chemistry|cell biology|dna|rna|clinic|pharmaceut)/i,
  ],
  // Robotics — embodied, manipulation, locomotion.
  [
    "robotics",
    /\b(robot|robotic|manipulation|dexterous|locomotion|embodied|quadruped|humanoid|teleop|grasp)/i,
  ],
  // 3D / graphics — must beat vision (a "3D diffusion model" is 3D first).
  [
    "3d",
    /\b(3d|gaussian splat|splatting|nerf|neural radiance|mesh|radiance field|volumetric|point cloud|pbr|texture synthesis|ray tracing|slam)/i,
  ],
  // Video / 4D / temporal generation.
  ["video", /\b(video|4d|temporal|motion generation|frame interpolation|optical flow)/i],
  // Audio / speech / music.
  [
    "audio",
    /\b(audio|speech|music|voice|tts|asr|sound|acoustic|song|instrument|melody|singing|lyrics)/i,
  ],
  // Vision / image generation (generic image stuff).
  [
    "vision",
    /\b(vision|image gener|diffusion model|segment|object detect|image-to-image|text-to-image|vlm|vision-language|ocr|depth estim)/i,
  ],
  // Agents / tool use / orchestration.
  [
    "agent",
    /\b(agent|multi-agent|tool use|mcp|orchestrat|autonomous|planning|workflow|runbook)/i,
  ],
  // LLM / reasoning / language.
  [
    "llm",
    /\b(llm|language model|reasoning|instruction tuning|chat|prompt|rag|retrieval[- ]augmented|transformer|fine-tune|code generation|gpt|claude|gemini|mistral|qwen|llama)/i,
  ],
];

/**
 * Infer the primary topic for an item. Falls back to the source category
 * when no keyword rule matches, then to "other".
 */
export function inferTopic(item: ScoredItem): Topic {
  const haystack = [
    item.title || "",
    item.summary || "",
    item.what_the_tech_does || "",
    item.description || "",
    (item.key_capabilities || []).join(" "),
  ]
    .join(" ")
    .toLowerCase();

  for (const [topic, rx] of RULES) {
    if (rx.test(haystack)) return topic;
  }

  // Source-category fallback buckets.
  const cat = (item.category || "").toLowerCase();
  if (cat === "browser") return "browser";
  if (cat === "dataset") return "dataset";
  if (cat === "tool") return "tool";
  return "other";
}

/**
 * Return the topics actually present in this item set, in the canonical
 * display order, with a count for each. Topics with zero items are
 * omitted so the chip row doesn't grow stale.
 */
export function topicCounts(items: ScoredItem[]): Array<{ topic: Topic; count: number }> {
  const counts = new Map<Topic, number>();
  for (const it of items) {
    const t = inferTopic(it);
    counts.set(t, (counts.get(t) || 0) + 1);
  }
  const order: Topic[] = [
    "bio",
    "robotics",
    "3d",
    "video",
    "audio",
    "vision",
    "agent",
    "llm",
    "browser",
    "dataset",
    "tool",
    "other",
  ];
  return order
    .filter((t) => (counts.get(t) || 0) > 0)
    .map((t) => ({ topic: t, count: counts.get(t) || 0 }));
}
