import type { DarkQuoteItem, TemplateOption, RoundInfo } from "../types";

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

export const TEMPLATES: TemplateOption[] = [
  { id: "career", title: "Career Change", question: "Should I stay or take the new offer?", pathA: "Stay at my current job", pathB: "Take the new opportunity", category: "financial" },
  { id: "city", title: "New City", question: "Should I move or stay put?", pathA: "Stay in my current city", pathB: "Move somewhere new", category: "financial" },
  { id: "startup", title: "Launch a Startup", question: "Should I go for it or play it safe?", pathA: "Stay employed", pathB: "Start my own thing", category: "financial" },
  { id: "education", title: "Education", question: "Should I study or keep working?", pathA: "Keep working", pathB: "Go back to school", category: "financial" },
  { id: "relationship", title: "Relationship", question: "Should I say something or let it go?", pathA: "Say what I feel", pathB: "Keep it to myself", category: "personal" },
  { id: "lifestyle", title: "Lifestyle Change", question: "Should I make the change or stay comfortable?", pathA: "Commit to the change", pathB: "Keep things as they are", category: "personal" },
];

export const ROUNDS: RoundInfo[] = [
  { name: "The Fork", title: "Opening Statements", description: "Both paths lay out their opening vision." },
  { name: "The Ledger", title: "The Money Talk", description: "The money talk \u2014 salary, savings, runway." },
  { name: "The Stranger", title: "Who Do You Become?", description: "Who do you become in each future?" },
  { name: "The Loop", title: "The Regret Test", description: "The regret test \u2014 what haunts you?" },
  { name: "The Knot", title: "Final Arguments", description: "Final arguments before the verdict." },
];

export const VALUES: string[] = [
  "Growth", "Money", "Freedom", "Family", "Health",
  "Adventure", "Impact", "Stability", "Creativity",
];

// In dev, Vite proxy handles /api/* → localhost:8000 (see vite.config.ts)
// In prod, VITE_API_URL points to CloudFront or API Gateway
export const API_BASE: string = import.meta.env.VITE_API_URL || "";

// Debate uses a separate Lambda Function URL (5-min timeout vs API Gateway's 29s)
// Falls back to API_BASE when served behind CloudFront (which proxies both)
export const DEBATE_BASE: string = import.meta.env.VITE_DEBATE_URL || API_BASE;
