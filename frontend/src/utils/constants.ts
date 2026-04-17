import type { DarkQuoteItem, RoundInfo } from "../types";

function normalizeServiceUrl(value: string | undefined): string {
  if (!value) return "";

  try {
    const url = new URL(value);
    const isHttps = url.protocol === "https:";
    const isLocalHttp = url.protocol === "http:" && /^localhost$|^127(?:\.\d{1,3}){3}$/.test(url.hostname);

    if (!isHttps && !isLocalHttp) {
      return "";
    }

    return url.href.replace(/\/$/, "");
  } catch {
    return "";
  }
}

export const DARK_QUOTES: DarkQuoteItem[] = [
  { text: "Everything is connected.", source: "Dark" },
  { text: "Every decision for something is a decision against something else.", source: "Dark" },
  { text: "What we know is a drop. What we don't know is an ocean.", source: "Isaac Newton" },
  { text: "I thought I had more time. Why does everyone say that?", source: "Dark" },
  { text: "People are peculiar creatures. All their actions are driven by desire, their character forged by pain.", source: "Dark" },
  { text: "Two roads diverged in a wood, and I — I took the one less traveled by.", source: "Robert Frost" },
  { text: "We're not free in what we do, because we're not free in what we want.", source: "Schopenhauer" },
  { text: "Life is the sum of all your choices.", source: "Albert Camus" },
  { text: "You've spent enough nights at 3am running scenarios. Time to watch them play out.", source: "Diverge" },
  { text: "Stop imagining the escape. See what's on the other side.", source: "Diverge" },
  { text: "The cost of not deciding is still a decision.", source: "Diverge" },
];

export const ROUNDS: RoundInfo[] = [
  { name: "The Ripple", title: "Year 1: The Ripple", description: "What happened in the first year after you chose." },
  { name: "The Ledger", title: "Year 2-3: The Ledger", description: "The honeymoon is over. What does this path actually cost?" },
  { name: "The Mirror", title: "Year 5: The Mirror", description: "Five years in. Who have you become on this path?" },
  { name: "The Ghost", title: "Year 10: The Ghost", description: "A full decade later. What still haunts or anchors you?" },
  { name: "The Knot", title: "Final Words: The Knot", description: "One last chance to make their case." },
];

export const VALUES: string[] = [
  "Growth", "Money", "Freedom", "Family", "Health",
  "Adventure", "Impact", "Stability", "Creativity",
];

export const CRISIS_RESOURCES = [
  { name: "988 Suicide & Crisis Lifeline", action: "Call or text 988", url: "https://988lifeline.org", available: "24/7, free, confidential" },
  { name: "Crisis Text Line", action: "Text HOME to 741741", url: "https://crisistextline.org", available: "24/7, free" },
  { name: "Emergency Services", action: "Call 911", url: null as string | null, available: "Immediate danger" },
  { name: "International Crisis Lines", action: "Find your country", url: "https://findahelpline.com", available: "Worldwide" },
];

// Default browser behavior is same-origin /api via Vite/Vercel/CloudFront rewrites.
// Set VITE_API_MODE=direct only for explicit live AWS smoke tests.
const USE_DIRECT_API = import.meta.env.VITE_API_MODE === "direct";

export const API_BASE: string = USE_DIRECT_API ? normalizeServiceUrl(import.meta.env.VITE_API_URL) : "";

// Long-running debate routes can still use a separate origin in direct smoke-test mode.
export const DEBATE_BASE: string = USE_DIRECT_API
  ? normalizeServiceUrl(import.meta.env.VITE_DEBATE_URL) || API_BASE
  : API_BASE;

export const CHECKPOINTED_DEBATE_ENABLED: boolean = import.meta.env.VITE_CHECKPOINTED_DEBATE === "true";
