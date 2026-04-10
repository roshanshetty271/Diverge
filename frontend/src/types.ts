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
  type: "book" | "video" | "article" | "podcast" | "concept";
  title: string;
  author: string;
  url?: string | null;
  why: string;
}

export interface ChronologicalTimelineStage {
  path_a_safe: string;
  path_b_bet: string;
}

export interface ChronologicalTimelineFinalStage extends ChronologicalTimelineStage {
  verdict_path_of_least_regret: string;
}

export interface ChronologicalTimelineExploreItem {
  type: "book" | "video" | "concept";
  title: string;
  author: string;
  why_it_helps: string;
  url: string;
}

export interface ChronologicalTimeline {
  stage_01_the_fork_year_1: ChronologicalTimelineStage;
  stage_02_the_ledger_year_3: ChronologicalTimelineStage;
  stage_03_the_mirror_year_5: ChronologicalTimelineStage;
  stage_04_the_ghost_year_10: ChronologicalTimelineStage;
  stage_05_the_knot_final_words: ChronologicalTimelineFinalStage;
  stage_06_what_to_explore_next: ChronologicalTimelineExploreItem[];
}

export interface DebateResponse {
  debate_id: string;
  transcript: RoundResult[];
  verdict: string;
  timeline?: ChronologicalTimeline | null;
  metrics: (RoundMetrics | null)[];
  completed_rounds: number;
  total_rounds: number;
  resources?: Resource[];
}

export interface CheckpointedDebateResponse {
  status: "paused" | "complete";
  debate_id: string;
  transcript: RoundResult[];
  verdict: string;
  timeline?: ChronologicalTimeline | null;
  metrics: (RoundMetrics | null)[];
  completed_rounds: number;
  total_rounds: number;
  resources?: Resource[];
  next_round_number?: number | null;
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

export interface Capabilities {
  active_provider: string;
  intended_provider: string;
  openai_fallback_active: boolean;
  bedrock_ready: boolean;
  tts: boolean;
  sentiment: boolean;
  email_checkins_ready: boolean;
  knowledge_base: boolean;
  agentcore_memory: boolean;
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
  summary?: string;
  date: string;
  source?: "cloud" | "local";
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
