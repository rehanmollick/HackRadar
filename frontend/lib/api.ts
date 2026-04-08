/**
 * Tiny fetch wrapper for the FastAPI backend.
 *
 * Routes are proxied through next.config.mjs rewrites in dev, so all calls
 * are made against the local Next server. No CORS hassle.
 */

const BASE = "/api";

export type ScanRow = {
  id: number;
  window_start: string;
  window_end: string;
  status: "running" | "done" | "error";
  sources: string[];
  started_at: string;
  finished_at: string | null;
  items_found: number | null;
  items_scored: number | null;
  error: string | null;
  focus_prompt: string | null;
};

export type ScoredItem = {
  id: number;
  title: string;
  description: string | null;
  source: string;
  source_url: string | null;
  github_url: string | null;
  huggingface_url: string | null;
  paper_url: string | null;
  demo_url: string | null;
  category: string | null;
  date: string;
  all_sources: string[];
  stars: number | null;
  language: string | null;
  license: string | null;
  total_score: number;
  open_score: number;
  novelty_score: number;
  wow_score: number;
  build_score: number;
  summary: string | null;
  hackathon_idea: string | null;
};

export type SourceHealth = {
  source: string;
  status: "OK" | "RED";
  last_success: string | null;
  last_failure: string | null;
  last_error: string | null;
  consecutive_failures: number;
  total_runs: number;
  total_failures: number;
};

export type ChatRow = { id: number; role: "user" | "assistant"; content: string; created_at: string };

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json();
}

export const api = {
  health: () => get<{ ok: boolean; missing_keys: string[]; sources_count: number }>("/health"),
  listScans: () => get<{ scans: ScanRow[] }>("/scans"),
  getScan: (id: number) => get<{ scan: ScanRow; items: ScoredItem[] }>(`/scans/${id}`),
  latestScan: () => get<{ scan: ScanRow; items: ScoredItem[] }>("/scans/latest"),
  startScan: (req: {
    from_date?: string;
    to_date?: string;
    lookback_hours?: number;
    source?: string;
    enrich?: boolean;
    focus_prompt?: string;
  }) => post<{ scan_id: number; status: string }>("/scans", req),
  getItem: (id: number) => get<{ item: ScoredItem; chats: ChatRow[] }>(`/items/${id}`),
  sourceHealth: () => get<{ sources: SourceHealth[] }>("/sources/health"),
};

/**
 * Stream a Pass 3 chat response. Yields raw text chunks as they arrive.
 * Caller drives the loop and renders incrementally.
 */
export async function* streamChat(
  itemId: number,
  message: string,
): AsyncIterableIterator<{ kind: "chunk" | "error" | "done"; data: string }> {
  const res = await fetch(`${BASE}/items/${itemId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE frames are separated by \n\n
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const lines = frame.split("\n");
      let event = "chunk";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trimStart();
      }
      if (event === "done") {
        yield { kind: "done", data };
        return;
      }
      yield { kind: event === "error" ? "error" : "chunk", data };
    }
  }
}

export function scoreClass(score: number): string {
  if (score >= 8) return "score-pill high";
  if (score >= 6) return "score-pill mid";
  return "score-pill low";
}
