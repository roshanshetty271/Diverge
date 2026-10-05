import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import LifeTimeline from "../components/LifeTimeline";
import ForkTimeline from "../components/ForkTimeline";
import { useDivergeAuth } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import {
  continueCheckpointedDebate,
  emailResults,
  getCheckpointedDebateSession,
  getCapabilities,
  saveDebate,
  scheduleCheckin,
  shareDebate,
  choosePath,
  submitFeedback,
} from "../utils/api";
import { generateDebatePdf } from "../utils/exportPdf";
import {
  hasAutosaved,
  loadDebateState,
  loadGutCheckState,
  markAutosaved,
  removeLocalJournalEntry,
  saveGutCheckState,
  saveLocalJournalEntry,
  storeDebateState,
} from "../utils/debateStorage";
import type {
  Capabilities,
  CheckpointedDebateResponse,
  ChronologicalTimeline,
  DebateResponse,
  DecisionInput,
  FinalizationProgress,
  Resource,
} from "../types";

const RE_BOLD = /\*\*/g;
const RE_HEADINGS = /^#{1,6}\s+/gm;
const RE_LIST_MARKERS = /^\s*[-*]\s+/gm;
const RE_MD_LINKS = /\[([^\]]+)\]\([^)]+\)/g;
const RE_INLINE_CODE = /`([^`]+)`/g;
const RE_POINT_PREFIX = /^\*?\*?[-•*]\s*/;
const RE_POINT_NUMBER = /^\d+[.)]\s*/;
const RE_LEADING_SEPARATOR = /^[:\s*]+/;

// Material Icon component for consistent iconography
const MaterialIcon = ({ name, className = "" }: { name: string; className?: string }) => (
  <span className={`material-icons ${className}`} aria-hidden="true">
    {name}
  </span>
);

// Resource type configuration for icons, colors, and styling
const RESOURCE_CONFIG: Record<string, {
  icon: string;
  iconColor: string;
  borderColor: string;
  badgeClass: string;
}> = {
  book: {
    icon: 'book',
    iconColor: 'text-path-safe',
    borderColor: 'border-path-safe/30',
    badgeClass: 'bg-path-safe/10 text-path-safe'
  },
  video: {
    icon: 'play_circle',
    iconColor: 'text-path-risk',
    borderColor: 'border-path-risk/30',
    badgeClass: 'bg-path-risk/10 text-path-risk'
  },
  concept: {
    icon: 'psychology',
    iconColor: 'text-ivory-dim',
    borderColor: 'border-ivory-dim/30',
    badgeClass: 'bg-ivory-dim/10 text-ivory-dim'
  },
  article: {
    icon: 'article',
    iconColor: 'text-ivory-dim',
    borderColor: 'border-ivory-dim/30',
    badgeClass: 'bg-ivory-dim/10 text-ivory-dim'
  },
  podcast: {
    icon: 'mic',
    iconColor: 'text-green-500',
    borderColor: 'border-green-500/30',
    badgeClass: 'bg-green-500/10 text-green-500'
  }
};

function stripMarkdown(text: string): string {
  return text
    .replace(RE_BOLD, "")
    .replace(RE_HEADINGS, "")
    .replace(RE_LIST_MARKERS, "")
    .replace(RE_MD_LINKS, "$1")
    .replace(RE_INLINE_CODE, "$1")
    .replace(/(?<!\w)--(?!\w)/g, " - ")
    .replace(/\u2014/g, " - ")
    .replace(/\u2013/g, " - ")
    .trim();
}

const TIMELINE_LABELS = ["Year 1", "Year 3", "Year 5", "Year 10", "Final Words", "Deathbed"];

function parseLifeSnapshot(verdictText: string, pathName: string): { label: string; text: string }[] {
  const marker = `life snapshot - ${pathName}`.toLowerCase();
  const lower = verdictText.toLowerCase();
  const idx = lower.indexOf(marker);
  if (idx === -1) return [];

  const afterMarker = verdictText.slice(idx + marker.length);
  const nextSectionIdx = afterMarker.search(/\n\s*\*\*[^*]/);
  const block = nextSectionIdx > 0 ? afterMarker.slice(0, nextSectionIdx) : afterMarker;

  const rows: { label: string; text: string }[] = [];
  for (const label of TIMELINE_LABELS) {
    const linePattern = new RegExp(`${label}\\s*:\\s*(.+)`, "i");
    const match = block.match(linePattern);
    if (match) {
      rows.push({ label, text: stripMarkdown(match[1].trim()) });
    }
  }
  return rows;
}

function parseLifeSnapshotBlock(block: string): { label: string; text: string }[] {
  if (!block) return [];

  const rows: { label: string; text: string }[] = [];
  for (const label of TIMELINE_LABELS) {
    const linePattern = new RegExp(`${label}\\s*:\\s*(.+)`, "i");
    const match = block.match(linePattern);
    if (match) {
      rows.push({ label, text: stripMarkdown(match[1].trim()) });
    }
  }
  return rows;
}

function mapStructuredTimelineRows(
  timeline: ChronologicalTimeline | null | undefined,
  pathKey: "path_a_safe" | "path_b_bet",
): { label: string; text: string }[] {
  if (!timeline) return [];

  const rows = [
    { label: "Year 1", text: timeline.stage_01_the_ripple_year_1[pathKey] },
    { label: "Year 3", text: timeline.stage_02_the_ledger_year_3[pathKey] },
    { label: "Year 5", text: timeline.stage_03_the_mirror_year_5[pathKey] },
    { label: "Year 10", text: timeline.stage_04_the_ghost_year_10[pathKey] },
    { label: "Final Words", text: timeline.stage_05_the_knot_final_words[pathKey] },
  ];

  return rows
    .map((row) => ({ label: row.label, text: stripMarkdown(row.text || "").trim() }))
    .filter((row) => row.text.length > 0);
}

function mapTimelineRecommendations(
  timeline: ChronologicalTimeline | null | undefined,
): Resource[] {
  if (!timeline?.stage_06_what_to_explore_next) return [];

  return timeline.stage_06_what_to_explore_next
    .map((item) => ({
      type: item.type,
      title: item.title,
      author: item.author,
      url: item.url,
      why: stripMarkdown(item.why_it_helps || "").trim(),
    }))
    .filter((item) => item.title && item.author && item.why);
}

function extractNamedSections(verdictText: string, headerRegex: RegExp): { heading: string; body: string }[] {
  const matches = Array.from(verdictText.matchAll(headerRegex));
  return matches.map((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = index + 1 < matches.length ? (matches[index + 1].index ?? verdictText.length) : verdictText.length;
    return {
      heading: stripMarkdown(match[1] || "").trim(),
      body: verdictText.slice(start, end).trim(),
    };
  });
}

// Stop polling for a pending verdict after this long and offer a retry instead.
const FINALIZATION_POLL_LIMIT_MS = 150_000;
const FINALIZATION_POLL_INTERVAL_MS = 1500;

function checkpointedToDebateResponse(result: CheckpointedDebateResponse): DebateResponse {
  return {
    debate_id: result.debate_id,
    transcript: result.transcript,
    verdict: result.verdict || "",
    timeline: result.timeline || null,
    metrics: result.metrics,
    completed_rounds: result.completed_rounds,
    total_rounds: result.total_rounds,
    resources: result.resources || [],
  };
}

export default function Verdict() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = (location.state || {}) as {
    debate?: DebateResponse;
    input?: DecisionInput;
    fromJournal?: boolean;
  };
  const stored = !locationState.debate ? loadDebateState() : null;
  const [debate, setDebate] = useState<DebateResponse | undefined>(locationState.debate || stored?.debate);
  const input = locationState.input || stored?.input;
  const initialGutCheck = debate?.debate_id ? loadGutCheckState(debate.debate_id) : null;
  const shouldSkipGutCheck = Boolean(locationState.fromJournal && debate?.verdict);
  const { isAuthenticated, isLoading: authLoading, token, login } = useDivergeAuth();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [saveSource, setSaveSource] = useState<"cloud" | "local" | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [checkinEmail, setCheckinEmail] = useState("");
  const [checkinSent, setCheckinSent] = useState(false);
  const [checkinSending, setCheckinSending] = useState(false);
  const [resultsEmail, setResultsEmail] = useState("");
  const [resultsSent, setResultsSent] = useState(false);
  const [resultsSending, setResultsSending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const [chosenPath, setChosenPath] = useState<string | null>(null);
  const [choosingPath, setChoosingPath] = useState(false);
  const [blindSpotRevealed, setBlindSpotRevealed] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState<string | null>(null);
  const [feedbackQuote, setFeedbackQuote] = useState("");
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [gutLeaning, setGutLeaning] = useState<string | null>(initialGutCheck?.leaning ?? null);
  const [gutFear, setGutFear] = useState(initialGutCheck?.fear ?? "");
  const [gutSubmitted, setGutSubmitted] = useState(initialGutCheck?.submitted ?? shouldSkipGutCheck);
  const [finalizationProgress, setFinalizationProgress] = useState<FinalizationProgress | null>(null);
  const [finalizationTimedOut, setFinalizationTimedOut] = useState(false);
  const [retryingFinalization, setRetryingFinalization] = useState(false);
  const [pollAttempt, setPollAttempt] = useState(0);

  useEffect(() => {
    if (!debate || !input || authLoading || !debate.verdict) return;
    const debateId = debate.debate_id;
    if (!debateId) return;

    let cancelled = false;

    const persist = async () => {
      if (isAuthenticated && token) {
        if (hasAutosaved("cloud", debateId)) {
          if (!cancelled) {
            setSaveSource("cloud");
          }
          return;
        }

        setSaving(true);
        try {
          await saveDebate({ debate_data: { ...debate, input } }, token);
          if (cancelled) return;
          markAutosaved("cloud", debateId);
          removeLocalJournalEntry(debateId);
          setSaveSource("cloud");
        } catch {
          if (!cancelled) {
            setSaveSource(null);
          }
        } finally {
          if (!cancelled) setSaving(false);
        }
        return;
      }

      if (hasAutosaved("local", debateId)) {
        if (!cancelled) {
          setSaveSource("local");
        }
        return;
      }

      saveLocalJournalEntry(debate, input);
      markAutosaved("local", debateId);
      if (!cancelled) {
        setSaveSource("local");
      }
    };

    void persist();
    return () => {
      cancelled = true;
    };
  }, [authLoading, debate, input, isAuthenticated, token]);

  useEffect(() => {
    let cancelled = false;

    getCapabilities()
      .then((result) => {
        if (!cancelled) setCapabilities(result);
      })
      .catch(() => {
        if (!cancelled) setCapabilities(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!debate?.debate_id || debate.verdict) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const startedAt = Date.now();
    setFinalizationTimedOut(false);

    const pollSession = async () => {
      try {
        const session = await getCheckpointedDebateSession(debate.debate_id);
        if (cancelled) return;

        if (session.finalization_progress) {
          setFinalizationProgress(session.finalization_progress);
        }

        if (session.verdict) {
          const updatedDebate = checkpointedToDebateResponse(session);
          setDebate(updatedDebate);
          if (input) {
            storeDebateState(updatedDebate, input);
          }
          return;
        }
      } catch {
        // Keep polling quietly while the verdict bundle finishes in the background.
      }

      if (cancelled) return;
      if (Date.now() - startedAt >= FINALIZATION_POLL_LIMIT_MS) {
        setFinalizationTimedOut(true);
        return;
      }
      timer = setTimeout(() => {
        void pollSession();
      }, FINALIZATION_POLL_INTERVAL_MS);
    };

    void pollSession();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [debate?.debate_id, debate?.verdict, input, pollAttempt]);

  useEffect(() => {
    if (!debate?.debate_id) return;

    const saved = loadGutCheckState(debate.debate_id);
    setGutLeaning(saved?.leaning ?? null);
    setGutFear(saved?.fear ?? "");
    setGutSubmitted(saved?.submitted ?? shouldSkipGutCheck);
  }, [debate?.debate_id, shouldSkipGutCheck]);

  useEffect(() => {
    if (!debate?.debate_id) return;

    saveGutCheckState(debate.debate_id, {
      leaning: gutLeaning,
      fear: gutFear,
      submitted: gutSubmitted,
    });
  }, [debate?.debate_id, gutFear, gutLeaning, gutSubmitted]);

  if (!debate) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-ivory-dim">The timeline has diverged. <button onClick={() => navigate("/decide")} className="text-path-risk underline cursor-pointer">Start over</button></p>
      </div>
    );
  }

  const verdictText = debate.verdict || "";
  const structuredTimeline = debate.timeline || null;
  const timelineVerdict = stripMarkdown(
    structuredTimeline?.stage_05_the_knot_final_words?.verdict_path_of_least_regret || "",
  );
  const pathAName = input?.path_a || "Option A";
  const pathBName = input?.path_b || "Option B";
  const verdictPending = debate.completed_rounds >= debate.total_rounds && verdictText.length === 0;

  const RE_HEADING_BOUNDARY = /\n\s*(?:\*\*[A-Z]|#{1,6}\s+[A-Z])/;

  const parseSection = (text: string, markers: string[], endMarkers: string[]): string => {
    if (!text) return "";
    const lowerText = text.toLowerCase();
    for (const marker of markers) {
      const idx = lowerText.indexOf(marker.toLowerCase());
      if (idx === -1) continue;
      const after = text.slice(idx + marker.length).replace(RE_LEADING_SEPARATOR, "");
      let best = after;
      const headingMatch = after.match(RE_HEADING_BOUNDARY);
      if (headingMatch && headingMatch.index != null && headingMatch.index > 0) {
        best = after.slice(0, headingMatch.index);
      }
      for (const end of endMarkers) {
        if (!end) continue;
        const endIdx = best.toLowerCase().indexOf(end.toLowerCase());
        if (endIdx > 0 && endIdx < best.length) best = best.slice(0, endIdx);
      }
      const result = best.trim();
      if (result.length > 5) return result;
    }
    return "";
  };

  const extractPoints = (text: string): string[] => {
    if (!text) return [];
    return text
      .split(/\n/)
      .map((l) => l.replace(RE_POINT_PREFIX, "").replace(RE_POINT_NUMBER, "").replace(RE_BOLD, "").trim())
      .filter((l) => l.length > 5)
      .slice(0, 3);
  };

  const sectionSeparators = [
    "what this decision is really about",
    "thing you",
    "hidden assumption",
    "not seeing",
    "blind spot",
    "the bottleneck",
    "question you",
    "your next move",
  ];
  const orderedWinSections = extractNamedSections(
    verdictText,
    /^\s*(?:\*\*)?Where\s+(.+?)\s+Wins:(?:\*\*)?\s*$/gim,
  );
  const orderedSnapshotSections = extractNamedSections(
    verdictText,
    /^\s*(?:\*\*)?Life Snapshot\s*-\s*(.+?):(?:\*\*)?\s*$/gim,
  );

  const winsA = extractPoints(
    parseSection(
      verdictText,
      ["Where staying wins", `Where ${pathAName} wins`, "Path A wins", "where option a wins"],
      [`Where ${pathBName}`, "Where jumping", "Path B wins", "where option b wins", ...sectionSeparators],
    ) || orderedWinSections[0]?.body || "",
  ).map(stripMarkdown);
  const winsB = extractPoints(
    parseSection(
      verdictText,
      ["Where jumping wins", `Where ${pathBName} wins`, "Path B wins", "where option b wins"],
      sectionSeparators,
    ) || orderedWinSections[1]?.body || "",
  ).map(stripMarkdown);
  const decisionCore = stripMarkdown(
    parseSection(
      verdictText,
      ["what this decision is really about", "not seeing", "might not be seeing", "hidden assumption", "blind spot", "thing you're missing"],
      ["the bottleneck", "question you", "overall", "your next move"],
    ),
  );
  const bottleneck = stripMarkdown(
    parseSection(verdictText, ["the bottleneck", "bottleneck"], ["your next move", "overall"]),
  );
  const blindSpot = [decisionCore, bottleneck].filter(Boolean).join(" ").trim() || timelineVerdict;
  const nextMove = stripMarkdown(parseSection(verdictText, ["your next move", "next move"], ["life snapshot", "\n\n**life"]));
  const snapshotA = parseLifeSnapshot(verdictText, pathAName).length > 0
    ? parseLifeSnapshot(verdictText, pathAName)
    : parseLifeSnapshotBlock(orderedSnapshotSections[0]?.body || "").length > 0
      ? parseLifeSnapshotBlock(orderedSnapshotSections[0]?.body || "")
      : mapStructuredTimelineRows(structuredTimeline, "path_a_safe");
  const snapshotB = parseLifeSnapshot(verdictText, pathBName).length > 0
    ? parseLifeSnapshot(verdictText, pathBName)
    : parseLifeSnapshotBlock(orderedSnapshotSections[1]?.body || "").length > 0
      ? parseLifeSnapshotBlock(orderedSnapshotSections[1]?.body || "")
      : mapStructuredTimelineRows(structuredTimeline, "path_b_bet");
  const hasTimeline = snapshotA.length >= 3 || snapshotB.length >= 3;
  const hasStructuredData = winsA.length > 0 || winsB.length > 0 || blindSpot.length > 20;

  const handleRetryFinalization = async () => {
    if (retryingFinalization) return;
    setRetryingFinalization(true);
    try {
      // Newer backends finish a stalled verdict here; older ones return the current state.
      const session = await continueCheckpointedDebate(debate.debate_id, undefined, debate.total_rounds);
      if (session.verdict) {
        const updatedDebate = checkpointedToDebateResponse(session);
        setDebate(updatedDebate);
        if (input) {
          storeDebateState(updatedDebate, input);
        }
      }
    } catch {
      // Fall back to polling below.
    } finally {
      setRetryingFinalization(false);
      setPollAttempt((n) => n + 1);
    }
  };

  const handleCheckin = async () => {
    if (!checkinEmail || checkinSending) return;
    setCheckinSending(true);
    try {
      await scheduleCheckin({
        email: checkinEmail,
        debate_id: debate.debate_id,
        path_a: pathAName,
        path_b: pathBName,
        micro_action: nextMove || "",
        user_name: input?.user_name || "",
      });
      setCheckinSent(true);
    } catch {
      toast("Couldn\u2019t schedule check-in. Try saving your debate instead.");
    } finally {
      setCheckinSending(false);
    }
  };

  const resources: Resource[] = (() => {
    const structuredRecommendations = mapTimelineRecommendations(structuredTimeline);
    if (structuredRecommendations.length > 0) {
      return structuredRecommendations.slice(0, 3);
    }
    return (debate.resources || []).slice(0, 3);
  })();

  const handleEmailResults = async () => {
    if (!resultsEmail || resultsSending) return;
    setResultsSending(true);
    try {
      const res = await emailResults({
        email: resultsEmail,
        path_a: pathAName,
        path_b: pathBName,
        verdict_summary: blindSpot || nextMove || stripMarkdown(verdictText).slice(0, 500),
        resources: resources.map((r) => ({ type: r.type, title: r.title, author: r.author, url: r.url, why: r.why })),
      });
      if (res.status === "sent") {
        setResultsSent(true);
      } else if (res.body) {
        await navigator.clipboard.writeText(res.body);
        setCopied(true);
        toast("Email not available \u2014 results copied to clipboard.");
      }
    } catch {
      toast("Couldn\u2019t send results. Try again later.");
    } finally {
      setResultsSending(false);
    }
  };

  const handleShare = async () => {
    if (sharing || shareUrl) return;
    setSharing(true);
    try {
      const res = await shareDebate(debate as unknown as Record<string, unknown>, (input || {}) as Record<string, unknown>);
      const fullUrl = `${window.location.origin}${res.url}`;
      setShareUrl(fullUrl);
      await navigator.clipboard.writeText(fullUrl);
      toast("Link copied to clipboard!");
    } catch {
      toast("Couldn\u2019t create share link. Try again.");
    } finally {
      setSharing(false);
    }
  };

  const handleChoosePath = async (path: string) => {
    if (choosingPath || !isAuthenticated || !token) return;
    setChoosingPath(true);
    try {
      const debateId = debate.debate_id;
      if (debateId) {
        await choosePath(debateId, path, token);
      }
      setChosenPath(path);
    } catch {
      toast("Couldn\u2019t record your choice. Try again.");
    } finally {
      setChoosingPath(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveDebate({ debate_data: { ...debate, input } }, token || undefined);
      if (debate.debate_id) {
        markAutosaved("cloud", debate.debate_id);
        removeLocalJournalEntry(debate.debate_id);
      }
      setSaveSource("cloud");
    } catch (err) {
      toast("Failed to save: " + (err instanceof Error ? err.message : "Unknown error"));
    } finally {
      setSaving(false);
    }
  };

  if (!gutSubmitted) {
    return (
      <div className="min-h-screen bg-void px-6 py-16 flex items-center justify-center">
        <div className="max-w-lg w-full border border-white/10 bg-surface/30 rounded-xl p-8">
          <p className="text-path-risk text-[10px] font-mono uppercase tracking-[0.3em] text-center mb-6">
            Before the verdict
          </p>
          <h2 className="font-display text-lg text-ivory text-center mb-8">
            Which way are you leaning right now?
          </h2>
          <div className="flex gap-4 justify-center mb-8">
            <button
              onClick={() => setGutLeaning(pathAName)}
              className={`px-5 py-3 rounded-lg border text-sm font-mono transition-all ${
                gutLeaning === pathAName
                  ? "border-path-safe text-path-safe shadow-[0_0_12px_rgba(74,111,165,0.2)]"
                  : "border-white/10 text-gray-400 hover:border-path-safe/50"
              }`}
            >
              {pathAName}
            </button>
            <button
              onClick={() => setGutLeaning(pathBName)}
              className={`px-5 py-3 rounded-lg border text-sm font-mono transition-all ${
                gutLeaning === pathBName
                  ? "border-path-risk text-path-risk shadow-[0_0_12px_rgba(212,168,67,0.2)]"
                  : "border-white/10 text-gray-400 hover:border-path-risk/50"
              }`}
            >
              {pathBName}
            </button>
          </div>
          <div className="mb-8">
            <label className="block text-ivory-dim text-sm mb-2">
              What&apos;s the one thing you&apos;re most afraid of?{" "}
              <span className="text-gray-500 text-xs">(optional)</span>
            </label>
            <textarea
              value={gutFear}
              onChange={(e) => setGutFear(e.target.value.slice(0, 200))}
              placeholder="The thing you keep coming back to..."
              className="w-full bg-transparent border-b border-white/10 text-ivory text-sm py-2 resize-none focus:outline-none focus:border-gray-500 placeholder:text-gray-600"
              rows={2}
            />
            <div className="flex justify-between mt-1">
              <p className="text-xs text-gray-500">This stays on your device. It&apos;s never sent anywhere.</p>
              <p className="text-xs font-mono text-gray-500">{gutFear.length} / 200</p>
            </div>
          </div>
          <button
            disabled={!gutLeaning}
            onClick={() => setGutSubmitted(true)}
            className="w-full py-3 rounded-lg bg-path-risk/90 text-void text-sm font-semibold uppercase tracking-wider hover:bg-path-risk transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Show me the verdict
          </button>
          <p className="text-xs text-gray-500 text-center mt-4 leading-relaxed">
            This helps you notice if the AI confirmed what you already believed<br />
            vs. genuinely shifted your thinking.
          </p>
        </div>
      </div>
    );
  }

  if (verdictPending && finalizationTimedOut) {
    return (
      <div className="min-h-screen bg-void px-6 py-16 flex items-center justify-center">
        <div className="max-w-lg w-full border border-white/10 bg-surface/30 rounded-xl p-8 text-center">
          <p className="text-path-risk text-[10px] font-mono uppercase tracking-[0.3em] mb-4">
            Final synthesis
          </p>
          <h2 className="font-display text-lg text-ivory mb-3">The verdict is taking longer than it should.</h2>
          <p className="text-ivory-dim text-sm leading-relaxed">
            Your debate is saved. Try again to finish the final readout.
          </p>
          <button
            onClick={() => { void handleRetryFinalization(); }}
            disabled={retryingFinalization}
            className="mt-6 px-6 py-3 rounded-lg text-sm border border-path-risk text-path-risk cursor-pointer transition-colors duration-200 hover:bg-path-risk hover:text-void disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none"
          >
            {retryingFinalization ? "Trying again\u2026" : "Try again"}
          </button>
        </div>
      </div>
    );
  }

  if (verdictPending) {
    const fp = finalizationProgress;
    const steps: Array<{ key: "verdict" | "timeline" | "resources"; label: string }> = [
      { key: "verdict", label: "Writing the verdict" },
      { key: "timeline", label: "Mapping the timeline" },
      { key: "resources", label: "Selecting resources" },
    ];

    return (
      <div className="min-h-screen bg-void px-6 py-16 flex items-center justify-center">
        <div className="max-w-lg w-full border border-white/10 bg-surface/30 rounded-xl p-8 text-center">
          <p className="text-path-risk text-[10px] font-mono uppercase tracking-[0.3em] mb-4">
            Final synthesis
          </p>
          <h2 className="font-display text-lg text-ivory mb-3">The verdict is still being written.</h2>
          <p className="text-ivory-dim text-sm leading-relaxed">
            The Knot is finished. We&apos;re turning the full debate into your final readout now.
          </p>
          {fp ? (
            <ul className="mt-6 space-y-2 text-left max-w-xs mx-auto">
              {steps.map(({ key, label }) => {
                const status = fp[key] ?? "running";
                if (status === "skipped") {
                  return (
                    <li key={key} className="flex items-center gap-3 text-sm text-ivory-faint">
                      <MaterialIcon name="block" className="text-base" />
                      <span className="italic">{label} skipped</span>
                    </li>
                  );
                }
                const isDone = status === "done";
                return (
                  <li key={key} className="flex items-center gap-3 text-sm">
                    <MaterialIcon
                      name={isDone ? "check_circle" : "pending"}
                      className={`text-base ${isDone ? "text-path-safe" : "text-path-risk animate-pulse"}`}
                    />
                    <span className={isDone ? "text-ivory-dim line-through" : "text-ivory"}>{label}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="mt-6 flex justify-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-path-risk animate-pulse" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-path-risk animate-pulse" style={{ animationDelay: "180ms" }} />
              <span className="w-2 h-2 rounded-full bg-path-risk animate-pulse" style={{ animationDelay: "360ms" }} />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-void px-6 py-16">
      <div className="max-w-5xl mx-auto">
        <StaggerGroup>
          {/* Gut-check reminder */}
          {gutLeaning && (
            <StaggerItem className="text-center mb-4">
              <p className="text-xs font-mono text-gray-500">
                You came in leaning toward <span className="text-ivory">{gutLeaning}</span>
              </p>
            </StaggerItem>
          )}

          {/* Dramatic Header Section */}
          <StaggerItem className="text-center mb-12">
            <h1 className="font-display text-4xl md:text-5xl font-bold text-ivory uppercase tracking-[0.15em] mb-2">
              THE VERDICT
            </h1>
            <p className="text-ivory-dim text-sm md:text-base italic tracking-wide">
              A cinematic revelation of your divergence
            </p>
          </StaggerItem>

          {/* Comparison Cards - Path Wins */}
          {hasStructuredData && (
            <StaggerItem className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Path A Wins Card */}
              <div className="bg-surface rounded-lg border-2 border-path-safe/30 p-5 hover:border-path-safe/50 transition-colors">
                <div className="flex items-center gap-3 mb-3">
                  <MaterialIcon name="shield" className="text-path-safe text-2xl" />
                  <h3 className="text-path-safe text-base font-semibold">
                    Where {pathAName} Wins
                  </h3>
                </div>
                <ul className="space-y-2">
                  {winsA.length > 0 ? (
                    winsA.map((point, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-path-safe mt-1">•</span>
                        <span className="text-ivory text-sm leading-relaxed">{point}</span>
                      </li>
                    ))
                  ) : (
                    <p className="text-ivory-dim text-sm italic">See full verdict below</p>
                  )}
                </ul>
              </div>

              {/* Path B Wins Card */}
              <div className="bg-surface rounded-lg border-2 border-path-risk/30 p-5 hover:border-path-risk/50 transition-colors">
                <div className="flex items-center gap-3 mb-3">
                  <MaterialIcon name="bolt" className="text-path-risk text-2xl" />
                  <h3 className="text-path-risk text-base font-semibold">
                    Where {pathBName} Wins
                  </h3>
                </div>
                <ul className="space-y-2">
                  {winsB.length > 0 ? (
                    winsB.map((point, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-path-risk mt-1">•</span>
                        <span className="text-ivory text-sm leading-relaxed">{point}</span>
                      </li>
                    ))
                  ) : (
                    <p className="text-ivory-dim text-sm italic">See full verdict below</p>
                  )}
                </ul>
              </div>
            </StaggerItem>
          )}

          {/* Blind Spot Callout Section */}
          <StaggerItem className="mt-10">
            <div className="bg-surface rounded-lg border border-surface-light border-l-4 border-l-path-risk p-6 relative">
              {/* Background decorative icon */}
              <MaterialIcon 
                name="visibility_off" 
                className="absolute right-6 top-6 text-path-risk/10 text-[100px] pointer-events-none overflow-hidden"
              />
              
              <div className="relative z-10">
                <p className="text-path-risk text-[10px] font-mono uppercase tracking-[0.3em] mb-2">
                  Critical Insight
                </p>
                <h2 className="font-display text-2xl md:text-3xl font-bold text-ivory uppercase tracking-wide mb-4">
                  THE BLIND SPOT
                </h2>
                
                {!blindSpotRevealed ? (
                  <>
                    <p className="text-ivory-dim text-sm md:text-base leading-relaxed mb-4 italic">
                      There's something you're not seeing. Are you ready to face it?
                    </p>
                    <button 
                      onClick={() => setBlindSpotRevealed(true)}
                      className="px-5 py-2.5 rounded-lg text-xs font-semibold uppercase tracking-wider bg-path-risk text-void hover:bg-path-risk/90 transition-all duration-200 flex items-center gap-2"
                    >
                      Confront Truth
                      <span className="text-base">→</span>
                    </button>
                  </>
                ) : (
                  <>
                    {gutFear && (
                      <p className="text-gray-400 text-sm italic mb-4 border-l-2 border-path-risk/30 pl-3">
                        You said you were afraid of: &ldquo;{gutFear}&rdquo;
                      </p>
                    )}
                    <p className="text-ivory text-sm md:text-base leading-relaxed">
                      {blindSpot || stripMarkdown(verdictText) || "The verdict is being prepared\u2026"}
                    </p>
                  </>
                )}
              </div>
            </div>
          </StaggerItem>

          {/* Timeline Section - Projection Matrix */}
          {hasTimeline && (
            <StaggerItem className="mt-12">
              <div className="text-center mb-6">
                <h2 className="text-ivory-faint text-xs font-mono uppercase tracking-[0.25em] mb-2">
                  Projection Matrix
                </h2>
                <p className="text-ivory-dim text-sm">
                  Tap a glowing node to reveal its future
                </p>
              </div>
              
              {/* Existing ForkTimeline component - NO CHANGES */}
              <ForkTimeline pathAName={pathAName} pathBName={pathBName} snapshotA={snapshotA} snapshotB={snapshotB} />
              
              <div className="mt-8">
                {/* Existing LifeTimeline component - NO CHANGES */}
                <LifeTimeline pathAName={pathAName} pathBName={pathBName} snapshotA={snapshotA} snapshotB={snapshotB} />
              </div>
            </StaggerItem>
          )}

          {/* Next Move Action Card */}
          {nextMove && (
            <StaggerItem className="mt-8">
              <div className="bg-surface rounded-lg border-2 border-path-risk/40 p-5 hover:border-path-risk/60 transition-colors">
                <div className="flex items-center gap-3 mb-3">
                  <MaterialIcon name="play_circle" className="text-path-risk text-3xl" />
                  <h3 className="text-path-risk text-lg font-semibold">
                    Your Next Move
                  </h3>
                </div>
                
                <p className="text-ivory text-sm md:text-base leading-relaxed mb-3">
                  {nextMove}
                </p>
                
                <p className="text-path-risk text-xs font-semibold uppercase tracking-wide">
                  Do this in the next 24 hours
                </p>
              </div>
            </StaggerItem>
          )}

          {/* Feedback */}
          {!feedbackSubmitted && (
            <StaggerItem className="mt-10">
              <div className="border border-white/10 bg-surface/30 rounded-xl p-6 max-w-xl mx-auto">
                <p className="text-path-risk text-[10px] font-mono uppercase tracking-[0.3em] mb-3 text-center">
                  Early signal
                </p>
                <h3 className="font-display text-base text-ivory text-center mb-5" style={{ fontWeight: 400 }}>
                  Did this change how you see it?
                </h3>
                {!feedbackRating ? (
                  <div className="flex gap-3 justify-center">
                    {[
                      { value: "shifted", label: "Yes, it shifted something" },
                      { value: "somewhat", label: "Somewhat" },
                      { value: "no", label: "Not really" },
                    ].map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => setFeedbackRating(opt.value)}
                        className="px-4 py-2.5 rounded-lg text-xs font-mono border border-white/10 text-gray-400 hover:border-path-risk/50 hover:text-ivory transition-colors cursor-pointer"
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                ) : !feedbackSubmitted ? (
                  <div>
                    <p className="text-ivory-dim text-sm text-center mb-3">In one line, what shifted?</p>
                    <div className="flex gap-2 max-w-md mx-auto">
                      <input
                        type="text"
                        value={feedbackQuote}
                        onChange={(e) => setFeedbackQuote(e.target.value.slice(0, 140))}
                        placeholder="Optional"
                        className="flex-1 bg-transparent border-b border-white/10 text-ivory text-sm py-2 focus:outline-none focus:border-gray-500 placeholder:text-gray-600"
                      />
                      <button
                        onClick={() => {
                          setFeedbackSubmitted(true);
                          if (debate?.debate_id) {
                            submitFeedback(debate.debate_id, feedbackRating!, feedbackQuote, isAuthenticated ? token : null).catch(() => {});
                          }
                        }}
                        className="px-4 py-2 rounded-lg text-xs font-mono border border-path-risk text-path-risk hover:bg-path-risk hover:text-void transition-colors cursor-pointer"
                      >
                        Submit
                      </button>
                    </div>
                    <p className="text-gray-500 text-xs text-center mt-2">
                      {feedbackQuote.length} / 140
                    </p>
                  </div>
                ) : null}
              </div>
            </StaggerItem>
          )}
          {feedbackSubmitted && (
            <StaggerItem className="mt-10">
              <p className="text-gray-500 text-sm italic text-center">
                Thank you. Your perspective helps us build better decision tools.
              </p>
            </StaggerItem>
          )}

          {/* Resources Section with Icons */}
          {resources.length > 0 && (
            <StaggerItem className="mt-10">
              <h2 className="text-ivory-faint text-[10px] font-mono uppercase tracking-[0.25em] mb-5 text-center">
                What to explore next
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {resources.map((resource, i) => {
                  const config = RESOURCE_CONFIG[resource.type] || {
                    icon: 'article',
                    iconColor: 'text-ivory-dim',
                    borderColor: 'border-ivory-dim/30',
                    badgeClass: 'bg-ivory-dim/10 text-ivory-dim'
                  };
                  
                  const card = (
                    <div className={`bg-surface rounded-lg border-2 ${config.borderColor} p-4 hover:scale-[1.02] transition-transform`}>
                      <div className="flex items-start justify-between mb-2">
                        <MaterialIcon name={config.icon} className={`${config.iconColor} text-xl`} />
                        <span className={`text-[9px] font-mono px-2 py-0.5 rounded ${config.badgeClass}`}>
                          {resource.type.toUpperCase()}
                        </span>
                      </div>
                      
                      <h4 className="text-ivory text-sm font-semibold mb-1 line-clamp-2">
                        {resource.title}
                      </h4>
                      <p className="text-ivory-dim text-xs mb-1">
                        {resource.author}
                      </p>
                      <p className="text-ivory-faint text-xs leading-relaxed line-clamp-3">
                        {resource.why}
                      </p>
                    </div>
                  );
                  
                  return resource.url ? (
                    <a 
                      key={i} 
                      href={resource.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      referrerPolicy="no-referrer"
                      className="block"
                    >
                      {card}
                    </a>
                  ) : (
                    <div key={i}>{card}</div>
                  );
                })}
              </div>
              {resultsSent ? (
                <p className="text-path-safe text-sm font-mono text-center mt-4">{"\u2713"} Full list sent to your email.</p>
              ) : copied ? (
                <p className="text-path-safe text-sm font-mono text-center mt-4">{"\u2713"} Results copied to clipboard.</p>
              ) : (
                <div className="flex gap-2 mt-4 max-w-md mx-auto">
                  <input
                    type="email"
                    value={resultsEmail}
                    onChange={(e) => setResultsEmail(e.target.value)}
                    placeholder="Email me the full list"
                    onKeyDown={(e) => e.key === "Enter" && handleEmailResults()}
                    className="flex-1 bg-surface border border-surface-light rounded-lg px-4 py-2.5 text-ivory text-sm focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                  />
                  <button
                    onClick={handleEmailResults}
                    disabled={!resultsEmail || resultsSending}
                    className="px-4 py-2.5 rounded-lg text-sm border border-path-risk text-path-risk cursor-pointer transition-colors duration-200 hover:bg-path-risk hover:text-void disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk"
                  >
                    {resultsSending ? "Sending\u2026" : "Send"}
                  </button>
                </div>
              )}
            </StaggerItem>
          )}

          {capabilities?.email_checkins_ready && (
            <StaggerItem className="mt-8">
              {checkinSent ? (
                <div className="text-center">
                  <p className="text-path-safe text-sm font-mono">{"\u2713"} We'll check in at Day 7, 30, and 90.</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-ivory-faint text-xs">Want us to check in with you?</p>
                  <div className="flex gap-2 w-full max-w-sm">
                    <input
                      type="email"
                      value={checkinEmail}
                      onChange={(e) => setCheckinEmail(e.target.value)}
                      placeholder="your@email.com"
                      onKeyDown={(e) => e.key === "Enter" && handleCheckin()}
                      className="flex-1 bg-surface border border-surface-light rounded-lg px-4 py-2.5 text-ivory text-sm focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                    />
                    <button
                      onClick={handleCheckin}
                      disabled={!checkinEmail || checkinSending}
                      className="px-4 py-2.5 rounded-lg text-sm border border-path-risk text-path-risk cursor-pointer transition-colors duration-200 hover:bg-path-risk hover:text-void disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk"
                    >
                      {checkinSending ? "Sending\u2026" : "Remind me"}
                    </button>
                  </div>
                  <p className="text-ivory-faint/50 text-[10px]">3 emails: Day 7, Day 30, Day 90. That's it.</p>
                </div>
              )}
            </StaggerItem>
          )}

          <StaggerItem className="mt-12 flex flex-wrap gap-3 justify-center">
            {saveSource === "cloud" && (
              <p className="text-path-safe text-sm font-mono">&#x2713; Saved to your journal</p>
            )}
            {saveSource === "local" && (
              <p className="text-path-safe text-sm font-mono">&#x2713; Saved on this device</p>
            )}
            {isAuthenticated ? (
              saveSource !== "cloud" && (
              <button 
                onClick={handleSave} 
                disabled={saving} 
                className="px-6 py-3 rounded-lg text-sm font-medium bg-path-safe/10 border-2 border-path-safe text-path-safe hover:bg-path-safe hover:text-void transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-safe focus-visible:ring-offset-2 focus-visible:ring-offset-void disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {saving ? "Saving…" : "Save to Cloud"}
              </button>
              )
            ) : (
              <button 
                onClick={() => login()} 
                className="px-6 py-3 rounded-lg text-sm font-medium bg-path-safe/10 border-2 border-path-safe text-path-safe hover:bg-path-safe hover:text-void transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-safe focus-visible:ring-offset-2 focus-visible:ring-offset-void"
              >
                {saveSource === "local" ? "Sign In to Sync" : "Sign In to Save"}
              </button>
            )}
            {shareUrl ? (
              <button 
                onClick={() => { navigator.clipboard.writeText(shareUrl); toast("Link copied!"); }} 
                className="px-6 py-3 rounded-lg text-sm font-medium border-2 border-ivory-dim text-ivory-dim hover:border-ivory hover:text-ivory transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ivory-dim focus-visible:ring-offset-2 focus-visible:ring-offset-void"
              >
                &#x2713; Link Copied &mdash; Copy Again
              </button>
            ) : (
              <button 
                onClick={handleShare} 
                disabled={sharing} 
                className="px-6 py-3 rounded-lg text-sm font-medium border-2 border-surface-light text-ivory-dim hover:border-ivory-dim hover:text-ivory transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ivory-dim focus-visible:ring-offset-2 focus-visible:ring-offset-void disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {sharing ? "Creating link…" : "Share This Debate"}
              </button>
            )}
            <button
              onClick={() => debate && generateDebatePdf(debate, input || null)}
              className="px-6 py-3 rounded-lg text-sm font-medium border-2 border-surface-light text-ivory-dim hover:border-ivory-dim hover:text-ivory transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ivory-dim focus-visible:ring-offset-2 focus-visible:ring-offset-void"
            >
              Download Report
            </button>
            <button 
              onClick={() => navigate("/decide")} 
              className="px-6 py-3 rounded-lg text-sm font-medium border-2 border-surface-light text-ivory-dim hover:border-ivory-dim hover:text-ivory transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ivory-dim focus-visible:ring-offset-2 focus-visible:ring-offset-void"
            >
              New Decision
            </button>
          </StaggerItem>

          {/* Outcome tracking: which path did you choose? */}
          {saveSource === "cloud" && !chosenPath && isAuthenticated && (
            <StaggerItem className="mt-8 text-center">
              <p className="text-ivory-dim text-sm mb-3">Which path did you choose?</p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => handleChoosePath(pathAName)}
                  disabled={choosingPath}
                  className="px-5 py-2.5 rounded-lg text-sm font-medium bg-path-safe/10 border-2 border-path-safe text-path-safe hover:bg-path-safe hover:text-void transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-safe focus-visible:ring-offset-2 focus-visible:ring-offset-void disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {pathAName}
                </button>
                <button
                  onClick={() => handleChoosePath(pathBName)}
                  disabled={choosingPath}
                  className="px-5 py-2.5 rounded-lg text-sm font-medium bg-path-risk/10 border-2 border-path-risk text-path-risk hover:bg-path-risk hover:text-void transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-risk focus-visible:ring-offset-2 focus-visible:ring-offset-void disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {pathBName}
                </button>
              </div>
            </StaggerItem>
          )}
          {chosenPath && (
            <StaggerItem className="mt-6 text-center">
              <p className="text-ivory-dim text-sm">You chose: <span className="text-ivory font-medium">{chosenPath}</span></p>
              <p className="text-ivory-faint text-xs mt-1">We&rsquo;ll check in with you to see how it goes.</p>
            </StaggerItem>
          )}

          {/* Ethical stance */}
          <StaggerItem className="mt-16 border-t border-white/5 pt-8">
            <div className="max-w-lg mx-auto text-center">
              <p className="text-path-risk text-[10px] font-mono uppercase tracking-[0.3em] mb-4">
                &mdash;&mdash; About this analysis &mdash;&mdash;
              </p>
              <p className="text-sm text-gray-400 leading-relaxed mb-4">
                Diverge is a thinking tool, not an oracle. It does not pick a side.
              </p>
              <ul className="text-sm text-gray-500 leading-relaxed text-left max-w-sm mx-auto space-y-1 mb-4">
                <li>&bull; All metrics are AI estimates extracted from debate arguments</li>
                <li>&bull; Quantitative tools inform the debate, not the scores</li>
                <li>&bull; Your lived experience matters more than any model output</li>
                <li>&bull; This is not therapy, medical, or legal advice</li>
              </ul>
              <p className="text-xs text-gray-400">
                In crisis?{" "}
                <a href="tel:988" className="text-path-risk hover:underline">Call 988</a>
                {" "}or text HOME to{" "}
                <a href="sms:741741" className="text-path-risk hover:underline">741741</a>
              </p>
            </div>
          </StaggerItem>

          <StaggerItem className="mt-10 text-center">
            <p className="font-display text-sm text-ivory-dim italic">Sic Mundus Creatus Est.</p>
            <p className="text-ivory-faint/50 text-xs italic mt-1">Thus your world is created.</p>
          </StaggerItem>
        </StaggerGroup>
      </div>
    </div>
  );
}
