// ── Backend API types (mirrors backend/app/schemas.py) ──────────

export interface PathMetrics {
  financial_confidence: number;
  happiness_estimate: number;
  growth_potential: number;
  regret_risk: number;
  values_alignment: number;
  key_insight: string;
}

export interface RoundMetrics {
  path_a: PathMetrics;
  path_b: PathMetrics;
}

export interface SentimentScores {
  positive: number;
  negative: number;
  neutral: number;
  mixed: number;
}

export interface RoundSentiment {
  path_a: SentimentScores;
  path_b: SentimentScores;
}

export interface RoundResult {
  round_number: number;
  round_name: string;
  round_title: string;
  alpha: string;
  beta: string;
  metrics: RoundMetrics | null;
  sentiment?: RoundSentiment | null;
  status: "completed" | "partial";
}

export interface Resource {
  type: "book" | "video" | "article" | "podcast";
  title: string;
  author: string;
  url?: string | null;
  why: string;
}

export interface DebateResponse {
  debate_id: string;
  transcript: RoundResult[];
  verdict: string;
  metrics: (RoundMetrics | null)[];
  completed_rounds: number;
  total_rounds: number;
  resources?: Resource[];
}

export interface DecisionInput {
  path_a: string;
  path_b: string;
  user_name: string | null;
  age?: number | null;
  financial_context: string | null;
  values: string | null;
  risk_level?: string;
  time_horizon?: string;
  constraints?: string | null;
  writing_samples: string | null;
}

export interface TemplateOption {
  id: string;
  title: string;
  question: string;
  pathA: string;
  pathB: string;
  category: "financial" | "personal";
}

// ── UI types ────────────────────────────────────────────────────

export interface DarkQuoteItem {
  text: string;
  source: string;
}

export interface RoundInfo {
  name: string;
  title: string;
  description: string;
}

export interface JournalEntry {
  id: string;
  pathA: string;
  pathB: string;
  lean?: string;
  date: string;
  data?: DebateResponse;
  input?: DecisionInput;
}

// ── Auth types ──────────────────────────────────────────────────

export interface DivAuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: unknown;
  error: Error | null;
  token: string | null;
  userId: string | null;
  email: string | null;
  login: () => void;
  logout: () => void;
}
