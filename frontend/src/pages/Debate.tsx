import { useState, lazy, Suspense } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import AgentMessage from "../components/AgentMessage";
import RoundNav from "../components/RoundNav";
import { ROUNDS } from "../utils/constants";
import { loadDebateState } from "../utils/debateStorage";
import type { DebateResponse, DecisionInput } from "../types";

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
  const stored = !locationState.debate ? loadDebateState() : null;
  const debate = locationState.debate || stored?.debate;
  const input = locationState.input || stored?.input;

  const [currentRound, setCurrentRound] = useState(1);
  const [activeChart, setActiveChart] = useState<ChartTab>("Radar");

  if (!debate || !debate.transcript) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-ivory-dim">The timeline has diverged. <button onClick={() => navigate("/decide")} className="text-path-risk underline cursor-pointer">Start over</button></p>
      </div>
    );
  }

  const transcript = debate.transcript;
  const allMetrics = debate.metrics || [];
  const safeRound = Math.max(1, Math.min(currentRound, transcript.length));
  const round = transcript[safeRound - 1];
  const roundName = round?.round_name || ROUNDS[safeRound - 1]?.name || `Round ${safeRound}`;
  const roundTitle = round?.round_title || ROUNDS[safeRound - 1]?.title || "";
  const roundDescription = ROUNDS[safeRound - 1]?.description || "";
  const completedRounds = transcript.map((_, i) => i + 1);
  const pathAName = input?.path_a || "Option A";
  const pathBName = input?.path_b || "Option B";

  const safeLabel = `The You Who Chose: ${pathAName.length > 30 ? pathAName.slice(0, 30) + "\u2026" : pathAName}`;
  const riskLabel = `The You Who Chose: ${pathBName.length > 30 ? pathBName.slice(0, 30) + "\u2026" : pathBName}`;
  const currentMetrics = allMetrics[safeRound - 1];
  const nextRound = transcript[safeRound];
  const nextRoundName = nextRound?.round_name || ROUNDS[safeRound]?.name;
  const activeTabInfo = CHART_TABS.find((t) => t.key === activeChart)!;

  return (
    <div className="min-h-screen bg-void px-4 py-8 md:px-8">
      <div className="max-w-5xl mx-auto">

        {/* Step indicator — reads names from API response, falls back to ROUNDS */}
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
        </div>

        {/* Round header — uses API round_name and round_title */}
        <div className="text-center mb-10">
          <p className="text-ivory-faint text-xs font-mono uppercase tracking-widest">Round {safeRound} of {transcript.length}</p>
          <h1 className="font-display text-2xl md:text-3xl text-ivory mt-1" style={{ fontWeight: 400 }}>{roundName}</h1>
          <p className="text-ivory-dim text-sm mt-1">{roundTitle}</p>
          {roundDescription && (
            <p className="text-ivory-faint text-xs mt-2 italic">{roundDescription}</p>
          )}
          {round?.status === "partial" && <p className="text-path-risk text-xs mt-2 font-mono">This round was only partially generated</p>}
        </div>

        {/* Debate columns */}
        <AnimatePresence mode="wait">
          <motion.div key={safeRound} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.6 }} className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8">
            <AgentMessage agentName={safeLabel} message={round?.alpha || ""} variant="safe" />
            <AgentMessage agentName={riskLabel} message={round?.beta || ""} variant="risk" />
          </motion.div>
        </AnimatePresence>

        {/* Charts */}
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

        {/* Round navigation */}
        <div className="mt-8"><RoundNav totalRounds={5} currentRound={safeRound} completedRounds={completedRounds} onRoundClick={setCurrentRound} /></div>

        {/* Next / Verdict button */}
        <div className="mt-8 text-center">
          {safeRound < transcript.length ? (
            <button onClick={() => setCurrentRound((p) => p + 1)} className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim hover:border-path-risk hover:text-ivory transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk">
              {nextRoundName ? `Next: ${nextRoundName}` : "Next round"} &rarr;
            </button>
          ) : (
            <button onClick={() => navigate("/verdict", { state: { debate, input } })} className="px-8 py-3 rounded-lg text-sm bg-path-risk text-void font-medium transition-[opacity,box-shadow] duration-200 cursor-pointer hover:shadow-[0_0_20px_rgba(212,168,67,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-risk focus-visible:ring-offset-2 focus-visible:ring-offset-void">See the Verdict</button>
          )}
        </div>
      </div>
    </div>
  );
}
