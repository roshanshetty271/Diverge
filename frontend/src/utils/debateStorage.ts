import type { DebateResponse, DecisionInput } from "../types";

const DEBATE_KEY = "diverge_debate";
const INPUT_KEY = "diverge_input";

interface StoredDebate {
  debate: DebateResponse;
  input: DecisionInput;
  timestamp: number;
}

const MAX_AGE_MS = 2 * 60 * 60 * 1000; // 2 hours

export function storeDebateState(debate: DebateResponse, input: DecisionInput): void {
  try {
    const data: StoredDebate = { debate, input, timestamp: Date.now() };
    sessionStorage.setItem(DEBATE_KEY, JSON.stringify(data));
  } catch {
    // sessionStorage full or unavailable — non-critical
  }
}

export function loadDebateState(): { debate: DebateResponse; input: DecisionInput } | null {
  try {
    const raw = sessionStorage.getItem(DEBATE_KEY);
    if (!raw) return null;
    const data: StoredDebate = JSON.parse(raw);
    if (Date.now() - data.timestamp > MAX_AGE_MS) {
      sessionStorage.removeItem(DEBATE_KEY);
      return null;
    }
    return { debate: data.debate, input: data.input };
  } catch {
    return null;
  }
}

export function clearDebateState(): void {
  sessionStorage.removeItem(DEBATE_KEY);
  sessionStorage.removeItem(INPUT_KEY);
}
