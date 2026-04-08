import type { DebateResponse, DecisionInput, JournalEntry } from "../types";

const DEBATE_KEY = "diverge_debate";
const INPUT_KEY = "diverge_input";
const LOCAL_JOURNAL_KEY = "diverge_local_journal";
const AUTOSAVE_PREFIX = "diverge_autosave";

interface StoredDebate {
  debate: DebateResponse;
  input: DecisionInput;
  timestamp: number;
}

const MAX_AGE_MS = 2 * 60 * 60 * 1000;
const LOCAL_JOURNAL_LIMIT = 50;

function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function buildSummary(debate: DebateResponse): string | undefined {
  const plain = stripMarkdown(debate.verdict || "");
  return plain ? plain.slice(0, 120) : undefined;
}

function readLocalJournal(): JournalEntry[] {
  try {
    const raw = localStorage.getItem(LOCAL_JOURNAL_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function writeLocalJournal(entries: JournalEntry[]): void {
  try {
    localStorage.setItem(LOCAL_JOURNAL_KEY, JSON.stringify(entries.slice(0, LOCAL_JOURNAL_LIMIT)));
  } catch {
    // localStorage full or unavailable
  }
}

function autosaveKey(target: "cloud" | "local", debateId: string): string {
  return `${AUTOSAVE_PREFIX}:${target}:${debateId}`;
}

export function storeDebateState(debate: DebateResponse, input: DecisionInput): void {
  try {
    const data: StoredDebate = { debate, input, timestamp: Date.now() };
    sessionStorage.setItem(DEBATE_KEY, JSON.stringify(data));
  } catch {
    // sessionStorage full or unavailable
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

export function saveLocalJournalEntry(debate: DebateResponse, input: DecisionInput): JournalEntry {
  const entry: JournalEntry = {
    id: debate.debate_id || `local-${Date.now()}`,
    pathA: input.path_a || "Option A",
    pathB: input.path_b || "Option B",
    summary: buildSummary(debate),
    date: new Date().toISOString(),
    source: "local",
    data: debate,
    input,
  };

  const existing = readLocalJournal().filter((item) => item.id !== entry.id);
  writeLocalJournal([entry, ...existing]);
  return entry;
}

export function loadLocalJournalEntries(): JournalEntry[] {
  return readLocalJournal();
}

export function removeLocalJournalEntry(debateId: string): void {
  const existing = readLocalJournal();
  writeLocalJournal(existing.filter((item) => item.id !== debateId));
}

export function hasAutosaved(target: "cloud" | "local", debateId: string): boolean {
  try {
    return localStorage.getItem(autosaveKey(target, debateId)) === "1";
  } catch {
    return false;
  }
}

export function markAutosaved(target: "cloud" | "local", debateId: string): void {
  try {
    localStorage.setItem(autosaveKey(target, debateId), "1");
  } catch {
    // localStorage unavailable
  }
}

export function clearDebateState(): void {
  sessionStorage.removeItem(DEBATE_KEY);
  sessionStorage.removeItem(INPUT_KEY);
}
