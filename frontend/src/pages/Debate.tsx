import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import AgentMessage from "../components/AgentMessage";
import RoundNav from "../components/RoundNav";
import { ROUNDS } from "../utils/constants";
import { loadDebateState, storeDebateState } from "../utils/debateStorage";
import { subscribeDebate, getDebateStream } from "../utils/debateStream";
import { getVoicePair, stopSpeaking } from "../utils/tts";
import type { DebateResponse, DecisionInput, RoundResult, RoundMetrics } from "../types";

const DecisionRadar = lazy(() => import("../components/DecisionRadar"));
const TimelineChart = lazy(() => import("../components/TimelineChart"));
const RegretChart = lazy(() => import("../components/RegretChart"));

const CHART_TABS = [
  { key: "Radar", label: "Radar", description: "How each path scores across five dimensions right now." },
  { key: "Timeline", label: "Timeline", description: "How happiness evolves across rounds." },
  { key: "Regret", label: "Regret", description: "Probability of regret for each path over time." },
] as const;
type ChartTab = (typeof CHART_TABS)[number]["key"];

export default function Debate() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = (location.state || {}) as { debate?: DebateResponse; input?: DecisionInput };

  const stream = getDebateStream();
  const stored = !locationState.debate && stream.rounds.length === 0 ? loadDebateState() : null;

  const isStreaming = stream.rounds.length > 0;

  const [, forceUpdate] = useState(0);
  const [currentRound, setCurrentRound] = useState(1);
  const [activeChart, setActiveChart] = useState<ChartTab>("Radar");
  const [visibleMessages, setVisibleMessages] = useState(0);
  const [skipped, setSkipped] = useState(false);

  const transcript: RoundResult[] = isStreaming ? stream.rounds : (locationState.debate?.transcript || stored?.debate?.transcript || []);
  const input: DecisionInput | undefined | null = isStreaming ? stream.input : (locationState.input || stored?.input);
  const allMetrics: (RoundMetrics | null)[] = isStreaming ? stream.metrics : (locationState.debate?.metrics || stored?.debate?.metrics || []);
  const verdictReady = isStreaming ? stream.done && !!stream.verdict : true;
  const debate: DebateResponse | undefined = isStreaming
    ? { debate_id: stream.debateId || "", transcript: stream.rounds, verdict: stream.verdict || "", metrics: stream.metrics, completed_rounds: stream.completedRounds, total_rounds: stream.totalRounds }
    : (locationState.debate || stored?.debate);

  const userName = input?.user_name || null;
  const [voiceA, voiceB] = getVoicePair(userName);

  useEffect(() => {
    const unsub = subscribeDebate(() => {
      forceUpdate((c) => c + 1);
      const s = getDebateStream();
      if (s.done && s.input && s.rounds.length > 0) {
        storeDebateState(
          { debate_id: s.debateId || "", transcript: s.rounds, verdict: s.verdict || "", metrics: s.metrics, completed_rounds: s.completedRounds, total_rounds: s.totalRounds },
          s.input,
        );
      }
    });
    return unsub;
  }, []);

  const revealAll = useCallback(() => {
    setVisibleMessages(2);
    setSkipped(true);
  }, []);

  useEffect(() => {
    setVisibleMessages(0);
    setSkipped(false);
    stopSpeaking();
    const t1 = setTimeout(() => setVisibleMessages(1), 500);
    const t2 = setTimeout(() => setVisibleMessages(2), 2500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [currentRound]);

  useEffect(() => {
    return () => stopSpeaking();
  }, []);

  if (transcript.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-ivory-dim">The timeline has diverged. <button onClick={() => navigate("/decide")} className="text-path-risk underline cursor-pointer">Start over</button></p>
      </div>
    );
  }

  const safeRound = Math.max(1, Math.min(currentRound, transcript.length));
  const round = transcript[safeRound - 1];
  const roundName = round?.round_name || ROUNDS[safeRound - 1]?.name || `Round ${safeRound}`;
  const roundTitle = round?.round_title || ROUNDS[safeRound - 1]?.title || "";
  const completedRounds = transcript.map((_, i) => i + 1);
  const pathAName = input?.path_a || "Option A";
  const pathBName = input?.path_b || "Option B";

  const safeLabel = pathAName.length > 30 ? pathAName.slice(0, 30) + "\u2026" : pathAName;
  const riskLabel = pathBName.length > 30 ? pathBName.slice(0, 30) + "\u2026" : pathBName;
  const currentMetrics = allMetrics[safeRound - 1];
  const nextRound = transcript[safeRound];
  const nextRoundName = nextRound?.round_name || ROUNDS[safeRound]?.name;
  const activeTabInfo = CHART_TABS.find((t) => t.key === activeChart)!;

  const heading = userName ? `${userName}\u2019s Decision` : "The Debate";

  const isLastAvailableRound = safeRound === transcript.length;
  const moreRoundsGenerating = isStreaming && !stream.done && isLastAvailableRound;
  const canGoVerdict = safeRound >= transcript.length && verdictReady;

  return (
    <div className="min-h-screen bg-void px-4 py-8 md:px-8">
      <div className="max-w-3xl mx-auto">

        <p className="text-center text-ivory-faint text-xs font-mono uppercase tracking-widest mb-1">{heading}</p>

        {/* Step indicator */}
        <div className="flex justify-center items-center gap-1 mb-8">
          {transcript.map((r, i) => {
            const stepNum = i + 1;
            const isActive = stepNum === safeRound;
            const isPast = stepNum < safeRound;
            const shortName = (r.round_name || ROUNDS[i]?.name || `R${stepNum}`).replace("The ", "");
            return (
              <div key={i} className="flex items-center gap-1">
                {i > 0 && <span className={`w-4 md:w-6 h-px ${isPast || isActive ? "bg-path-risk" : "bg-surface-light"}`} />}
                <button
                  onClick={() => stepNum <= transcript.length && setCurrentRound(stepNum)}
                  className={`text-[10px] md:text-xs font-mono transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk rounded ${
                    isActive
                      ? "text-path-risk font-medium"
                      : isPast
                        ? "text-ivory-dim hover:text-ivory"
                        : "text-ivory-faint/40 cursor-default"
                  }`}
                >
                  {shortName}
                </button>
              </div>
            );
          })}
          {isStreaming && !stream.done && (
            <div className="flex items-center gap-1">
              <span className="w-4 md:w-6 h-px bg-surface-light" />
              <span className="text-[10px] font-mono text-ivory-faint/40 animate-pulse">
                {transcript.length + 1 <= 5 ? `R${transcript.length + 1}…` : "…"}
              </span>
            </div>
          )}
        </div>

        {/* Round header */}
        <div className="text-center mb-8">
          <p className="text-ivory-faint text-xs font-mono uppercase tracking-widest">Round {safeRound} of {stream.totalRounds || 5}</p>
          <h1 className="font-display text-2xl md:text-3xl text-ivory mt-1" style={{ fontWeight: 400 }}>{roundName}</h1>
          <p className="text-ivory-dim text-sm mt-1">{roundTitle}</p>
          {round?.status === "partial" && <p className="text-path-risk text-xs mt-2 font-mono">This round was only partially generated</p>}
        </div>

        {/* Chat bubbles */}
        <AnimatePresence mode="wait">
          <motion.div key={safeRound} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }} className="space-y-5">
            {visibleMessages >= 1 && (
              <AgentMessage agentName={safeLabel} message={round?.alpha || ""} variant="safe" voiceId={voiceA} />
            )}
            {visibleMessages >= 2 && (
              <AgentMessage agentName={riskLabel} message={round?.beta || ""} variant="risk" voiceId={voiceB} />
            )}
          </motion.div>
        </AnimatePresence>

        {/* Skip button */}
        {visibleMessages < 2 && !skipped && (
          <div className="mt-4 text-center">
            <button onClick={revealAll} className="text-ivory-faint text-xs font-mono hover:text-ivory-dim transition-colors cursor-pointer">
              Skip &rarr;
            </button>
          </div>
        )}

        {/* Next / Generating / Verdict button */}
        {visibleMessages >= 2 && (
          <div className="mt-8 text-center">
            {moreRoundsGenerating ? (
              <p className="text-ivory-faint text-xs font-mono animate-pulse">Generating next round&hellip;</p>
            ) : canGoVerdict ? (
              <button onClick={() => navigate("/verdict", { state: { debate, input } })} className="px-8 py-3 rounded-lg text-sm bg-path-risk text-void font-medium transition-[opacity,box-shadow] duration-200 cursor-pointer hover:shadow-[0_0_20px_rgba(212,168,67,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-risk focus-visible:ring-offset-2 focus-visible:ring-offset-void">See the Verdict</button>
            ) : safeRound < transcript.length ? (
              <button onClick={() => setCurrentRound((p) => p + 1)} className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim hover:border-path-risk hover:text-ivory transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk">
                {nextRoundName ? `Next: ${nextRoundName}` : "Next round"} &rarr;
              </button>
            ) : !verdictReady ? (
              <p className="text-ivory-faint text-xs font-mono animate-pulse">Generating verdict&hellip;</p>
            ) : null}
          </div>
        )}

        {/* Charts */}
        {visibleMessages >= 2 && (
          <div className="mt-10">
            <div className="flex gap-1 mb-2">
              {CHART_TABS.map((tab) => (
                <button key={tab.key} onClick={() => setActiveChart(tab.key)}
                  className={`px-4 py-2 text-xs font-mono uppercase tracking-wider transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk rounded ${activeChart === tab.key ? "text-ivory border-b-2 border-path-risk" : "text-ivory-faint border-b-2 border-transparent hover:text-ivory-dim"}`}>
                  {tab.label}
                </button>
              ))}
            </div>
            <p className="text-ivory-faint text-[11px] font-mono mb-3 pl-1">{activeTabInfo.description}</p>
            <div className="bg-surface rounded-lg border border-surface-light p-4 md:p-6">
              <Suspense fallback={<div className="h-[280px] flex items-center justify-center text-ivory-faint text-sm font-mono">Loading chart&hellip;</div>}>
                {activeChart === "Radar" && <DecisionRadar metricsA={currentMetrics?.path_a || null} metricsB={currentMetrics?.path_b || null} pathAName={pathAName} pathBName={pathBName} />}
                {activeChart === "Timeline" && <TimelineChart allMetrics={allMetrics.slice(0, safeRound)} pathAName={pathAName} pathBName={pathBName} />}
                {activeChart === "Regret" && <RegretChart allMetrics={allMetrics.slice(0, safeRound)} pathAName={pathAName} pathBName={pathBName} />}
              </Suspense>
            </div>
          </div>
        )}

        {/* Round navigation */}
        {visibleMessages >= 2 && (
          <div className="mt-8"><RoundNav totalRounds={transcript.length} currentRound={safeRound} completedRounds={completedRounds} onRoundClick={setCurrentRound} /></div>
        )}
      </div>
    </div>
  );
}
