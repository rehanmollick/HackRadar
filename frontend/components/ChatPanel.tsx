"use client";

import { useState } from "react";
import { ChatRow, streamChat } from "../lib/api";

export default function ChatPanel({
  itemId,
  initialChats,
}: {
  itemId: number;
  initialChats: ChatRow[];
}) {
  const [chats, setChats] = useState<ChatRow[]>(initialChats);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!draft.trim() || busy) return;
    setBusy(true);
    setError(null);
    const userTurn: ChatRow = {
      id: Date.now(),
      role: "user",
      content: draft,
      created_at: new Date().toISOString(),
    };
    setChats((prev) => [...prev, userTurn]);
    const message = draft;
    setDraft("");
    setStreaming("");

    try {
      let assembled = "";
      for await (const ev of streamChat(itemId, message)) {
        if (ev.kind === "chunk") {
          assembled += ev.data;
          setStreaming(assembled);
        } else if (ev.kind === "error") {
          setError(ev.data);
          break;
        }
      }
      if (assembled) {
        setChats((prev) => [
          ...prev,
          {
            id: Date.now() + 1,
            role: "assistant",
            content: assembled,
            created_at: new Date().toISOString(),
          },
        ]);
      }
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally {
      setStreaming("");
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-stone-200 bg-white p-5">
      <h3 className="mb-3 font-mono text-sm font-bold uppercase tracking-wider text-stone-500">
        Deep dive (Claude)
      </h3>

      <div className="space-y-3">
        {chats.length === 0 && !streaming && (
          <p className="text-sm text-stone-500">
            Ask anything about this technology — what to build, the closest
            competitor, the demo gotchas, the prep checklist.
          </p>
        )}
        {chats.map((c) => (
          <div
            key={c.id}
            className={
              c.role === "user"
                ? "rounded-md bg-stone-100 px-3 py-2 text-sm"
                : "rounded-md border border-stone-200 px-3 py-2 text-sm"
            }
          >
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-stone-500">
              {c.role}
            </div>
            <div className="whitespace-pre-wrap text-stone-800">{c.content}</div>
          </div>
        ))}
        {streaming && (
          <div className="rounded-md border border-stone-200 px-3 py-2 text-sm">
            <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-stone-500">
              assistant
            </div>
            <div className="whitespace-pre-wrap text-stone-800">{streaming}▍</div>
          </div>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask Claude…"
          className="flex-1 rounded-md border border-stone-300 px-3 py-2 text-sm"
          disabled={busy}
        />
        <button onClick={send} disabled={busy || !draft.trim()} className="btn btn-primary">
          {busy ? "…" : "Send"}
        </button>
      </div>
    </section>
  );
}
