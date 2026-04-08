import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import LifeTimeline from "../components/LifeTimeline";
import ForkTimeline from "../components/ForkTimeline";
import { useDivergeAuth } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import {
  emailResults,
  getCapabilities,
  saveDebate,
  scheduleCheckin,
  shareDebate,
  choosePath,
} from "../utils/api";
import { generateDebatePdf } from "../utils/exportPdf";
import {
  hasAutosaved,
  loadDebateState,
  markAutosaved,
  removeLocalJournalEntry,
  saveLocalJournalEntry,
} from "../utils/debateStorage";
import type { Capabilities, DebateResponse, DecisionInput, Resource } from "../types";

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

const TIMELINE_LABELS = ["Year 1", "Year 3", "Year 5", "Year 10", "Deathbed"];

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

export default function Verdict() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = (location.state || {}) as { debate?: DebateResponse; input?: DecisionInput };
  const stored = !locationState.debate ? loadDebateState() : null;
  const debate = locationState.debate || stored?.debate;
  const input = locationState.input || stored?.input;
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

  useEffect(() => {
    if (!debate || !input || authLoading) return;
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

  if (!debate) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-ivory-dim">The timeline has diverged. <button onClick={() => navigate("/decide")} className="text-path-risk underline cursor-pointer">Start over</button></p>
      </div>
    );
  }

  const verdictText = debate.verdict || "";
  const pathAName = input?.path_a || "Option A";
  const pathBName = input?.path_b || "Option B";

  const parseSection = (text: string, markers: string[], endMarkers: string[]): string => {
    if (!text) return "";
    const lowerText = text.toLowerCase();
    for (const marker of markers) {
      const idx = lowerText.indexOf(marker.toLowerCase());
      if (idx === -1) continue;
      const after = text.slice(idx + marker.length).replace(RE_LEADING_SEPARATOR, "");
      let best = after;
      for (const end of endMarkers) {
        if (!end) continue;
        const endIdx = after.toLowerCase().indexOf(end.toLowerCase());
        if (endIdx > 0 && endIdx < best.length) best = after.slice(0, endIdx);
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

  const sectionSeparators = ["thing you", "hidden assumption", "not seeing", "blind spot", "question you"];
  const winsA = extractPoints(parseSection(verdictText, ["Where staying wins", `Where ${pathAName} wins`, "Path A wins", "where option a wins"], [`Where ${pathBName}`, "Where jumping", "Path B wins", "where option b wins", ...sectionSeparators])).map(stripMarkdown);
  const winsB = extractPoints(parseSection(verdictText, ["Where jumping wins", `Where ${pathBName} wins`, "Path B wins", "where option b wins"], sectionSeparators)).map(stripMarkdown);
  const blindSpot = stripMarkdown(parseSection(verdictText, ["not seeing", "might not be seeing", "hidden assumption", "blind spot", "thing you're missing"], ["question you", "overall"]));
  const nextMove = stripMarkdown(parseSection(verdictText, ["your next move", "next move"], ["life snapshot", "\n\n**life"]));
  const snapshotA = parseLifeSnapshot(verdictText, pathAName);
  const snapshotB = parseLifeSnapshot(verdictText, pathBName);
  const hasTimeline = snapshotA.length >= 3 || snapshotB.length >= 3;
  const hasStructuredData = winsA.length > 0 || winsB.length > 0 || blindSpot.length > 20;

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

  const resources: Resource[] = (debate.resources || []).slice(0, 3);

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

  return (
    <div className="min-h-screen bg-void px-6 py-16">
      <div className="max-w-5xl mx-auto">
        <StaggerGroup>
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
                  <p className="text-ivory text-sm md:text-base leading-relaxed">
                    {blindSpot || stripMarkdown(verdictText) || "The verdict is being prepared…"}
                  </p>
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

          {!hasStructuredData && verdictText && (
            <StaggerItem className="mt-8"><div className="text-ivory text-base leading-[1.75] whitespace-pre-line">{stripMarkdown(verdictText)}</div></StaggerItem>
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

          <StaggerItem className="mt-16 text-center">
            <p className="font-display text-sm text-ivory-dim italic">Sic Mundus Creatus Est.</p>
            <p className="text-ivory-faint/50 text-xs italic mt-1">Thus your world is created.</p>
          </StaggerItem>
        </StaggerGroup>
      </div>
    </div>
  );
}
