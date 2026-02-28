import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import LifeTimeline from "../components/LifeTimeline";
import { useDivergeAuth } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import { saveDebate, scheduleCheckin } from "../utils/api";
import { loadDebateState } from "../utils/debateStorage";
import type { DebateResponse, DecisionInput } from "../types";

const RE_BOLD = /\*\*/g;
const RE_HEADINGS = /^#{1,6}\s+/gm;
const RE_LIST_MARKERS = /^\s*[-*]\s+/gm;
const RE_MD_LINKS = /\[([^\]]+)\]\([^)]+\)/g;
const RE_INLINE_CODE = /`([^`]+)`/g;
const RE_POINT_PREFIX = /^\*?\*?[-•*]\s*/;
const RE_POINT_NUMBER = /^\d+[.)]\s*/;
const RE_LEADING_SEPARATOR = /^[:\s*]+/;

function stripMarkdown(text: string): string {
  return text
    .replace(RE_BOLD, "")
    .replace(RE_HEADINGS, "")
    .replace(RE_LIST_MARKERS, "")
    .replace(RE_MD_LINKS, "$1")
    .replace(RE_INLINE_CODE, "$1")
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
  const { isAuthenticated, token, userId, login } = useDivergeAuth();
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [checkinEmail, setCheckinEmail] = useState("");
  const [checkinSent, setCheckinSent] = useState(false);
  const [checkinSending, setCheckinSending] = useState(false);

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

  const sectionSeparators = ["thing you", "hidden assumption", "not seeing", "blind spot", "Based on", "lean toward", "question you"];
  const winsA = extractPoints(parseSection(verdictText, ["Where staying wins", `Where ${pathAName} wins`, "Path A wins", "where option a wins"], [`Where ${pathBName}`, "Where jumping", "Path B wins", "where option b wins", ...sectionSeparators])).map(stripMarkdown);
  const winsB = extractPoints(parseSection(verdictText, ["Where jumping wins", `Where ${pathBName} wins`, "Path B wins", "where option b wins"], sectionSeparators)).map(stripMarkdown);
  const blindSpot = stripMarkdown(parseSection(verdictText, ["not seeing", "might not be seeing", "hidden assumption", "blind spot", "thing you're missing"], ["Based on", "lean toward", "question you", "overall"]));
  const lean = stripMarkdown(parseSection(verdictText, ["lean toward", "probably lean", "you'd lean", "you would lean", "i'd lean", "my lean", "i'd tell", "what i'd tell"], ["question you", "should actually", "reframed", "\n\n**"]));
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

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveDebate({ debate_data: { ...debate, input } }, token || undefined);
      setSaved(true);
    } catch (err) {
      toast("Failed to save: " + (err instanceof Error ? err.message : "Unknown error"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-void px-6 py-16">
      <div className="max-w-2xl mx-auto">
        <StaggerGroup>
          <StaggerItem className="text-center">
            <div className="w-16 h-px bg-path-risk mx-auto" />
            <p className="text-ivory-faint text-xs font-mono uppercase tracking-[0.25em] mt-4">The Verdict</p>
          </StaggerItem>

          {hasStructuredData && (
            <StaggerItem className="mt-12 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="border-l-2 border-path-safe pl-5 py-2">
                <p className="text-path-safe text-sm font-medium mb-3">Where {pathAName} wins</p>
                <div className="space-y-2">{winsA.length > 0 ? winsA.map((p, i) => <p key={i} className="text-ivory text-sm leading-relaxed"><span className="text-path-safe mr-2">·</span>{p}</p>) : <p className="text-ivory-dim text-sm italic">See full verdict below</p>}</div>
              </div>
              <div className="border-l-2 border-path-risk pl-5 py-2">
                <p className="text-path-risk text-sm font-medium mb-3">Where {pathBName} wins</p>
                <div className="space-y-2">{winsB.length > 0 ? winsB.map((p, i) => <p key={i} className="text-ivory text-sm leading-relaxed"><span className="text-path-risk mr-2">·</span>{p}</p>) : <p className="text-ivory-dim text-sm italic">See full verdict below</p>}</div>
              </div>
            </StaggerItem>
          )}

          <StaggerItem className="mt-12">
            <div className="bg-surface rounded-lg border border-surface-light border-l-4 border-l-path-risk p-6">
              <p className="text-path-risk text-sm font-medium mb-3">The thing you might not be seeing</p>
              <p className="text-ivory text-base leading-[1.75]">{blindSpot || stripMarkdown(verdictText) || "The verdict is being prepared\u2026"}</p>
            </div>
          </StaggerItem>

          {hasTimeline && (
            <StaggerItem className="mt-12">
              <p className="text-ivory-faint text-xs font-mono uppercase tracking-[0.2em] mb-6 text-center">Where each path takes you</p>
              <LifeTimeline pathAName={pathAName} pathBName={pathBName} snapshotA={snapshotA} snapshotB={snapshotB} />
            </StaggerItem>
          )}

          {lean && (
            <StaggerItem className="mt-10">
              <p className="text-ivory-dim text-sm">{input?.user_name ? `Here's what I'd tell ${input.user_name}:` : "Here's what I'd tell a friend in your position:"}</p>
              <p className="font-display text-lg text-path-risk mt-1" style={{ fontWeight: 500 }}>{lean}</p>
            </StaggerItem>
          )}

          {nextMove && (
            <StaggerItem className="mt-10">
              <div className="bg-surface rounded-lg border border-surface-light border-l-4 border-l-path-risk p-6">
                <p className="text-path-risk text-sm font-medium mb-3">Your next move</p>
                <p className="text-ivory text-base leading-[1.75]">{nextMove}</p>
                <p className="text-ivory-faint text-xs mt-3">Do this in the next 24 hours.</p>
              </div>
            </StaggerItem>
          )}

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

          {!hasStructuredData && verdictText && (
            <StaggerItem className="mt-8"><div className="text-ivory text-base leading-[1.75] whitespace-pre-line">{stripMarkdown(verdictText)}</div></StaggerItem>
          )}

          <StaggerItem className="mt-12 flex gap-3 justify-center">
            {saved ? (
              <p className="text-path-safe text-sm font-mono">✓ Saved to your journal</p>
            ) : isAuthenticated ? (
              <button onClick={handleSave} disabled={saving} className="px-6 py-3 rounded-lg text-sm border border-path-safe text-ivory cursor-pointer transition-colors duration-200 hover:border-ivory disabled:opacity-50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-safe">
                {saving ? "Saving\u2026" : "Save This Debate"}
              </button>
            ) : (
              <button onClick={() => login()} className="px-6 py-3 rounded-lg text-sm border border-path-safe text-ivory cursor-pointer transition-colors duration-200 hover:border-ivory focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-safe">Sign In to Save</button>
            )}
            <button onClick={() => navigate("/decide")} className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer transition-colors duration-200 hover:border-ivory-dim focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ivory-dim">New Decision</button>
          </StaggerItem>

          <StaggerItem className="mt-16 text-center">
            <p className="font-display text-sm text-ivory-dim italic">Sic Mundus Creatus Est.</p>
            <p className="text-ivory-faint/50 text-xs italic mt-1">Thus your world is created.</p>
          </StaggerItem>
        </StaggerGroup>
      </div>
    </div>
  );
}