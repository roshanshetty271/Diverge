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
  streamingAlphaDone: boolean;
  streamingBetaDone: boolean;
  // User interjections per round (keyed by round number)
  interjections: Record<number, string>;
  // Three-flag state model
  usingStreamState: boolean;
  isActivelyStreaming: boolean;
  streamingContinue: boolean;
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
    streamingAlphaDone: false, streamingBetaDone: false,
    interjections: {},
    usingStreamState: false, isActivelyStreaming: false, streamingContinue: false,
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

/** Process SSE events from the reader — shared between start and continue streams. */
function processSSEEvents(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onStreamEnd: () => void,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";
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

  return (async () => {
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
            state = { ...state, debateId: event.debate_id, totalRounds: event.total_rounds };
            notify();

          } else if (event.type === "interjection") {
            notify();

          } else if (event.type === "round_start") {
            flushBatch();
            state = {
              ...state,
              streamingRound: event.round,
              streamingAlphaText: "",
              streamingBetaText: "",
              streamingAlphaDone: false,
              streamingBetaDone: false,
              streamingAgent: "alpha",
            };
            notify();

          } else if (event.type === "token") {
            const agent = event.agent as "alpha" | "beta";
            if (batchAgent !== agent) { flushBatch(); batchAgent = agent; }
            tokenBatch += event.text;
            if (batchTimer) clearTimeout(batchTimer);
            batchTimer = setTimeout(flushBatch, 80);

          } else if (event.type === "verdict_token") {
            if (batchAgent !== "verdict") { flushBatch(); batchAgent = "verdict"; }
            tokenBatch += event.text;
            if (batchTimer) clearTimeout(batchTimer);
            batchTimer = setTimeout(flushBatch, 80);

          } else if (event.type === "agent_done") {
            flushBatch();
            const agent = event.agent as "alpha" | "beta";
            state = {
              ...state,
              streamingAgent: null,
              streamingAlphaDone: agent === "alpha" ? true : state.streamingAlphaDone,
              streamingBetaDone: agent === "beta" ? true : state.streamingBetaDone,
            };
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
              completedRounds: state.rounds.length + 1,
              streamingAgent: null,
              streamingAlphaText: "",
              streamingBetaText: "",
              streamingAlphaDone: true,
              streamingBetaDone: true,
            };
            notify();

          } else if (event.type === "session_update") {
            // Non-final round complete — stream is closing, debate is paused
            flushBatch();
            state = {
              ...state,
              completedRounds: event.completed_rounds,
              totalRounds: event.total_rounds,
              done: false,
              isActivelyStreaming: false,
              streamingContinue: false,
              streamingAgent: null,
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
              isActivelyStreaming: false,
              streamingContinue: false,
              streamingAgent: null,
              streamingVerdictText: "",
            };
            notify();

          } else if (event.type === "error") {
            flushBatch();
            state = {
              ...state,
              error: event.message,
              done: state.streamingContinue ? state.done : true,
              isActivelyStreaming: false,
              streamingContinue: false,
            };
            notify();
          }
        } catch { /* malformed event, skip */ }
      }
    }

    flushBatch();
    onStreamEnd();
  })();
}

export async function startDebateStream(payload: DecisionInput, captchaToken?: string | null): Promise<void> {
  resetDebateStream();
  state = { ...state, input: payload, usingStreamState: true, isActivelyStreaming: true, streamingContinue: false };
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
        state = { ...state, error: "__crisis__", done: true, isActivelyStreaming: false };
        notify();
        return;
      }
    }

    if (!res.body) throw new Error("No response stream");

    await processSSEEvents(res.body.getReader(), () => {
      if (!state.done) {
        state = { ...state, done: true, isActivelyStreaming: false };
        notify();
      }
    });
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      state = { ...state, error: (err as Error).message, done: true, isActivelyStreaming: false, streamingContinue: false };
      notify();
    }
  }
}

export async function startCheckpointedStream(payload: DecisionInput, captchaToken?: string | null): Promise<void> {
  resetDebateStream();
  state = { ...state, input: payload, usingStreamState: true, isActivelyStreaming: true, streamingContinue: false };
  abortCtrl = new AbortController();

  try {
    const res = await fetch(`${DEBATE_BASE}/api/debate/session/start-stream`, {
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
        state = { ...state, error: "__crisis__", done: true, isActivelyStreaming: false };
        notify();
        return;
      }
    }

    if (!res.body) throw new Error("No response stream");

    await processSSEEvents(res.body.getReader(), () => {
      // Round 1 ends with session_update (paused); do NOT set done:true here.
      if (state.isActivelyStreaming) {
        state = { ...state, isActivelyStreaming: false, streamingContinue: false };
        notify();
      }
    });
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      state = { ...state, error: (err as Error).message, isActivelyStreaming: false, streamingContinue: false };
      notify();
    }
  }
}

export async function continueDebateStream(
  debateId: string,
  existingRounds: RoundResult[],
  existingMetrics: (RoundMetrics | null)[],
  input: DecisionInput,
  interjection?: string,
): Promise<void> {
  // Clear stale transient state but preserve rounds/metrics
  if (abortCtrl) { abortCtrl.abort(); abortCtrl = null; }
  state = {
    ...state,
    rounds: existingRounds,
    metrics: existingMetrics,
    verdict: null,
    timeline: null,
    resources: [],
    done: false,
    input,
    debateId,
    completedRounds: existingRounds.length,
    totalRounds: Math.max(state.totalRounds || 0, existingRounds.length, 5),
    error: null,
    streamingAlphaText: "",
    streamingBetaText: "",
    streamingVerdictText: "",
    streamingAlphaDone: false,
    streamingBetaDone: false,
    streamingAgent: null,
    usingStreamState: true,
    isActivelyStreaming: true,
    streamingContinue: true,
  };
  notify();
  abortCtrl = new AbortController();

  try {
    const res = await fetch(`${DEBATE_BASE}/api/debate/session/${debateId}/continue-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interjection: interjection || null }),
      signal: abortCtrl.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: `Error ${res.status}` }));
      throw new Error(typeof errData.detail === "string" ? errData.detail : `Server error ${res.status}`);
    }

    if (!res.body) throw new Error("No response stream");

    await processSSEEvents(res.body.getReader(), () => {
      // Stream ended — clear active flags but don't set done (unless complete event already did)
      if (state.isActivelyStreaming) {
        state = { ...state, isActivelyStreaming: false, streamingContinue: false };
        notify();
      }
    });
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      state = { ...state, error: (err as Error).message, isActivelyStreaming: false, streamingContinue: false };
      notify();
      throw err; // Re-throw so Debate.tsx can catch and toast
    }
  }
}
