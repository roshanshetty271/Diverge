import { API_BASE, DEBATE_BASE } from "./constants";
import type { DebateResponse, DecisionInput } from "../types";

const DEBATE_TIMEOUT_MS = 150_000;
const DEFAULT_TIMEOUT_MS = 15_000;

interface FetchOptions extends RequestInit {
  _timeout?: number;
}

async function apiFetch<T>(url: string, options: FetchOptions = {}): Promise<T> {
  const timeout = options._timeout || DEFAULT_TIMEOUT_MS;
  const controller = options.signal ? null : new AbortController();
  const signal = options.signal || controller?.signal;
  const timer = controller ? setTimeout(() => controller.abort(), timeout) : null;

  try {
    const res = await fetch(url, {
      ...options,
      signal,
      headers: { "Content-Type": "application/json", ...options.headers },
    });

    if (!res.ok) {
      let errorMessage: string;
      try {
        const errorData = await res.json();
        errorMessage = typeof errorData.detail === "string"
          ? errorData.detail
          : errorData.detail?.message || errorData.message || `Error ${res.status}`;
      } catch {
        errorMessage = res.status === 429
          ? "Too many requests. Please wait a few minutes."
          : `Server error (${res.status}). Please try again.`;
      }
      throw new Error(errorMessage);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error("Request was cancelled.");
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function startDebate(input: DecisionInput, signal?: AbortSignal): Promise<DebateResponse> {
  return apiFetch<DebateResponse>(`${DEBATE_BASE}/api/debate/start`, {
    method: "POST",
    body: JSON.stringify(input),
    signal,
    _timeout: DEBATE_TIMEOUT_MS,
  });
}

export async function getTemplates(): Promise<unknown[]> {
  return apiFetch<unknown[]>(`${API_BASE}/api/templates`);
}

export interface JournalResponse {
  items: Record<string, unknown>[];
  last_key?: Record<string, string>;
}

export async function getJournal(token: string, limit: number = 50): Promise<JournalResponse> {
  return apiFetch<JournalResponse>(`${API_BASE}/api/journal?limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function saveDebate(debateData: Record<string, unknown>, token?: string): Promise<unknown> {
  return apiFetch<unknown>(`${API_BASE}/api/debate/save`, {
    method: "POST",
    body: JSON.stringify(debateData),
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export interface CheckinPayload {
  email: string;
  path_a: string;
  path_b: string;
  micro_action: string;
  user_name: string;
}

export async function scheduleCheckin(payload: CheckinPayload): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>(`${API_BASE}/api/checkin`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface EmailResultsPayload {
  email: string;
  path_a: string;
  path_b: string;
  verdict_summary: string;
  resources: { type: string; title: string; author: string; url?: string | null; why: string }[];
}

export async function emailResults(payload: EmailResultsPayload): Promise<{ status: string; message: string; body?: string }> {
  return apiFetch<{ status: string; message: string; body?: string }>(`${API_BASE}/api/email-results`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
