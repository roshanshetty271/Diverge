import { DEBATE_BASE } from "./constants";
import type { RoundResult, RoundMetrics, DecisionInput, Resource } from "../types";

export interface DebateStreamState {
  rounds: RoundResult[];
  metrics: (RoundMetrics | null)[];
  verdict: string | null;
  debateId: string | null;
  completedRounds: number;
  totalRounds: number;
  done: boolean;
  error: string | null;
  input: DecisionInput | null;
  resources: Resource[];
}

let state: DebateStreamState = emptyState();
const listeners = new Set<() => void>();
let abortCtrl: AbortController | null = null;

function emptyState(): DebateStreamState {
  return {
    rounds: [], metrics: [], verdict: null, debateId: null,
    completedRounds: 0, totalRounds: 5, done: false, error: null, input: null,
    resources: [],
  };
}

function notify() { listeners.forEach((cb) => cb()); }

export function subscribeDebate(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

export function getDebateStream(): Readonly<DebateStreamState> {
  return state;
}

export function resetDebateStream() {
  if (abortCtrl) { abortCtrl.abort(); abortCtrl = null; }
  state = emptyState();
}

export async function startDebateStream(payload: DecisionInput): Promise<void> {
  resetDebateStream();
  state.input = payload;
  abortCtrl = new AbortController();

  try {
    const res = await fetch(`${DEBATE_BASE}/api/debate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: abortCtrl.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
      throw new Error(typeof errData.detail === "string" ? errData.detail : `Server error ${res.status}`);
    }

    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const jsonBody = await res.json();
      if (jsonBody.type === "crisis") {
        state = { ...state, error: "__crisis__", done: true };
        notify();
        return;
      }
    }

    if (!res.body) throw new Error("No response stream");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop()!;

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;

        try {
          const event = JSON.parse(line.slice(6));

          if (event.type === "round") {
            state = { ...state, rounds: [...state.rounds, event.data], metrics: [...state.metrics, event.data.metrics || null] };
            notify();
          } else if (event.type === "complete") {
            state = {
              ...state,
              verdict: event.verdict,
              debateId: event.debate_id,
              completedRounds: event.completed_rounds,
              totalRounds: event.total_rounds,
              metrics: event.metrics || state.metrics,
              resources: event.resources || [],
              done: true,
            };
            notify();
          } else if (event.type === "error") {
            state = { ...state, error: event.message, done: true };
            notify();
          }
        } catch { /* malformed event, skip */ }
      }
    }

    if (!state.done) {
      state = { ...state, done: true };
      notify();
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      state = { ...state, error: (err as Error).message, done: true };
      notify();
    }
  }
}
