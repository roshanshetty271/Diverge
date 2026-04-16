import { DEBATE_BASE } from "./constants";
import type { RoundResult, RoundMetrics, DecisionInput, Resource, ChronologicalTimeline } from "../types";

export interface DebateStreamState {
  rounds: RoundResult[];
  metrics: (RoundMetrics | null)[];
  verdict: string | null;
  timeline: ChronologicalTimeline | null;
  debateId: string | null;
  completedRounds: number;
  totalRounds: number;
  done: boolean;
  error: string | null;
  input: DecisionInput | null;
  resources: Resource[];
  // Token-streaming state
  streamingAgent: "alpha" | "beta" | "verdict" | null;
  streamingRound: number;
  streamingAlphaText: string;
  streamingBetaText: string;
  streamingVerdictText: string;
  // User interjections per round (keyed by round number)
  interjections: Record<number, string>;
}

let state: DebateStreamState = emptyState();
const listeners = new Set<() => void>();
let abortCtrl: AbortController | null = null;

function emptyState(): DebateStreamState {
  return {
    rounds: [], metrics: [], verdict: null, debateId: null,
    timeline: null,
    completedRounds: 0, totalRounds: 5, done: false, error: null, input: null,
    resources: [],
    streamingAgent: null, streamingRound: 0,
    streamingAlphaText: "", streamingBetaText: "", streamingVerdictText: "",
    interjections: {},
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

export function addInterjection(round: number, text: string) {
  state = { ...state, interjections: { ...state.interjections, [round]: text } };
  notify();
}

export async function startDebateStream(payload: DecisionInput, captchaToken?: string | null): Promise<void> {
  resetDebateStream();
  state.input = payload;
  abortCtrl = new AbortController();

  try {
    const res = await fetch(`${DEBATE_BASE}/api/debate/stream-tokens`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(captchaToken ? { "X-Captcha-Token": captchaToken } : {}),
      },
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

    // Batch token updates to avoid excessive re-renders
    let tokenBatch = "";
    let batchAgent: "alpha" | "beta" | "verdict" | null = null;
    let batchTimer: ReturnType<typeof setTimeout> | null = null;

    const flushBatch = () => {
      if (!tokenBatch || !batchAgent) return;
      if (batchAgent === "alpha") {
        state = { ...state, streamingAlphaText: state.streamingAlphaText + tokenBatch, streamingAgent: "alpha" };
      } else if (batchAgent === "beta") {
        state = { ...state, streamingBetaText: state.streamingBetaText + tokenBatch, streamingAgent: "beta" };
      } else if (batchAgent === "verdict") {
        state = { ...state, streamingVerdictText: state.streamingVerdictText + tokenBatch, streamingAgent: "verdict" };
      }
      tokenBatch = "";
      notify();
    };

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

          if (event.type === "debate_start") {
            state = {
              ...state,
              debateId: event.debate_id,
              totalRounds: event.total_rounds,
            };
            notify();

          } else if (event.type === "interjection") {
            // Server echo — interjection was picked up
            notify();

          } else if (event.type === "round_start") {
            flushBatch();
            state = {
              ...state,
              streamingRound: event.round,
              streamingAlphaText: "",
              streamingBetaText: "",
              streamingAgent: null,
            };
            notify();

          } else if (event.type === "token") {
            const agent = event.agent as "alpha" | "beta";
            if (batchAgent !== agent) {
              flushBatch();
              batchAgent = agent;
            }
            tokenBatch += event.text;
            if (batchTimer) clearTimeout(batchTimer);
            batchTimer = setTimeout(flushBatch, 80);

          } else if (event.type === "verdict_token") {
            if (batchAgent !== "verdict") {
              flushBatch();
              batchAgent = "verdict";
            }
            tokenBatch += event.text;
            if (batchTimer) clearTimeout(batchTimer);
            batchTimer = setTimeout(flushBatch, 80);

          } else if (event.type === "agent_done") {
            flushBatch();
            state = { ...state, streamingAgent: null };
            notify();

          } else if (event.type === "verdict_start") {
            flushBatch();
            state = { ...state, streamingVerdictText: "", streamingAgent: "verdict" };
            notify();

          } else if (event.type === "round_complete") {
            flushBatch();
            const roundData = event.data as RoundResult;
            state = {
              ...state,
              rounds: [...state.rounds, roundData],
              metrics: [...state.metrics, roundData.metrics || null],
              streamingAgent: null,
              streamingAlphaText: "",
              streamingBetaText: "",
            };
            notify();

          } else if (event.type === "complete") {
            flushBatch();
            state = {
              ...state,
              verdict: event.verdict,
              timeline: (event.timeline as ChronologicalTimeline | null) || null,
              debateId: event.debate_id,
              completedRounds: event.completed_rounds,
              totalRounds: event.total_rounds,
              metrics: event.metrics || state.metrics,
              resources: event.resources || [],
              done: true,
              streamingAgent: null,
              streamingVerdictText: "",
            };
            notify();

          } else if (event.type === "error") {
            flushBatch();
            state = { ...state, error: event.message, done: true };
            notify();
          }
        } catch { /* malformed event, skip */ }
      }
    }

    flushBatch();
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
