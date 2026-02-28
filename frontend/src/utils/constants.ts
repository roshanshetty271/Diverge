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
  { name: "The Fork", title: "Year 1: The Aftermath", description: "What happened in the first year after you chose." },
  { name: "The Reality", title: "Year 2-3: The Reality Check", description: "The honeymoon is over. What's the real cost?" },
  { name: "The Stranger", title: "Year 5: Who You Became", description: "Five years in. You're a different person now." },
  { name: "The Loop", title: "Year 10: The Regret Test", description: "A full decade. What did this path cost you?" },
  { name: "The Knot", title: "Final Words", description: "One last chance to make their case." },
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

// In dev, Vite proxy handles /api/* → localhost:8000 (see vite.config.ts)
// In prod, VITE_API_URL points to CloudFront or API Gateway
export const API_BASE: string = import.meta.env.VITE_API_URL || "";

// Debate uses a separate Lambda Function URL (5-min timeout vs API Gateway's 29s)
// Falls back to API_BASE when served behind CloudFront (which proxies both)
export const DEBATE_BASE: string = import.meta.env.VITE_DEBATE_URL || API_BASE;
