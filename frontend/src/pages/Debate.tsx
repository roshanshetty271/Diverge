import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import AgentMessage from "../components/AgentMessage";
import RoundNav from "../components/RoundNav";
import { ROUNDS } from "../utils/constants";
import { loadDebateState, storeDebateState } from "../utils/debateStorage";
import { subscribeDebate, getDebateStream, addInterjection } from "../utils/debateStream";
import { getVoicePair, stopSpeaking } from "../utils/tts";
import { sendInterjection } from "../utils/api";
import type { DebateResponse, DecisionInput, RoundResult, RoundMetrics } from "../types";

const DecisionRadar = lazy(() => import("../components/DecisionRadar"));
const TimelineChart = lazy(() => import("../components/TimelineChart"));
const RegretChart = lazy(() => import("../components/RegretChart"));
const SentimentChart = lazy(() => import("../components/SentimentChart"));

const CHART_TABS = [
  { key: "Radar", label: "Radar", description: "How each path scores across five dimensions right now." },
  { key: "Timeline", label: "Timeline", description: "How happiness evolves across rounds." },
  { key: "Regret", label: "Regret", description: "Probability of regret for each path over time." },
  { key: "Sentiment", label: "Sentiment", description: "Emotional tone of each path's arguments (via Amazon Comprehend)." },
] as const;
type ChartTab = (typeof CHART_TABS)[number]["key"];

export default function Debate() {
  const location = useLocation();
  const navigate = useNavigate();
  const locationState = (location.state || {}) as { debate?: DebateResponse; input?: DecisionInput };

  const stream = getDebateStream();
  const stored = !locationState.debate && stream.rounds.length === 0 ? loadDebateState() : null;

  const isStreaming = stream.rounds.length > 0 || stream.streamingAgent !== null || stream.streamingRound > 0;

  const [, forceUpdate] = useState(0);
  const [currentRound, setCurrentRound] = useState(1);
  const [activeChart, setActiveChart] = useState<ChartTab>("Radar");
  const [visibleMessages, setVisibleMessages] = useState(0);
  const [skipped, setSkipped] = useState(false);
  const [interjectionText, setInterjectionText] = useState("");
  const [interjectionSent, setInterjectionSent] = useState<Record<number, boolean>>({});

  const transcript: RoundResult[] = isStreaming ? stream.rounds : (locationState.debate?.transcript || stored?.debate?.transcript || []);
  const input: DecisionInput | undefined | null = isStreaming ? stream.input : (locationState.input || stored?.input);
  const allMetrics: (RoundMetrics | null)[] = isStreaming ? stream.metrics : (locationState.debate?.metrics || stored?.debate?.metrics || []);
  const verdictReady = isStreaming ? stream.done && !!stream.verdict : true;
  const debate: DebateResponse | undefined = isStreaming
    ? { debate_id: stream.debateId || "", transcript: stream.rounds, verdict: stream.verdict || "", metrics: stream.metrics, completed_rounds: stream.completedRounds, total_rounds: stream.totalRounds }
    : (locationState.debate || stored?.debate);

  const userName = input?.user_name || null;
  const [voiceA, voiceB] = getVoicePair(userName);

  // Is the current round being actively streamed right now?
  const isCurrentRoundStreaming = isStreaming && stream.streamingRound === currentRound;
  const alphaIsStreaming = isCurrentRoundStreaming && stream.streamingAgent === "alpha";
  const betaIsStreaming = isCurrentRoundStreaming && stream.streamingAgent === "beta";
  const hasStreamingAlpha = isCurrentRoundStreaming && stream.streamingAlphaText.length > 0;
  const hasStreamingBeta = isCurrentRoundStreaming && stream.streamingBetaText.length > 0;

  useEffect(() => {
    const unsub = subscribeDebate(() => {
      forceUpdate((c) => c + 1);
      const s = getDebateStream();

      // Auto-advance to the round being streamed
      if (s.streamingRound > 0) {
        setCurrentRound(s.streamingRound);
      }

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

  // For non-streaming mode, reveal messages with a delay
  useEffect(() => {
    if (isCurrentRoundStreaming) {
      setVisibleMessages(2);
      setSkipped(true);
      return;
    }
    setVisibleMessages(0);
    setSkipped(false);
    stopSpeaking();
    const t1 = setTimeout(() => setVisibleMessages(1), 500);
    const t2 = setTimeout(() => setVisibleMessages(2), 2500);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [currentRound, isCurrentRoundStreaming]);

  useEffect(() => {
    return () => stopSpeaking();
  }, []);

  // Determine what to show for the current round
  const completedRound = transcript[currentRound - 1];
  const hasCompletedRound = !!completedRound;

  // Use streaming text if we're on the active streaming round, otherwise use completed text
  const alphaText = hasCompletedRound
    ? completedRound.alpha
    : (isCurrentRoundStreaming ? stream.streamingAlphaText : "");
  const betaText = hasCompletedRound
    ? completedRound.beta
    : (isCurrentRoundStreaming ? stream.streamingBetaText : "");

  // Show alpha as soon as streaming or completed text exists
  const showAlpha = alphaText.length > 0 || alphaIsStreaming;
  const showBeta = betaText.length > 0 || betaIsStreaming;

  if (!isStreaming && transcript.length === 0) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-ivory-dim">The timeline has diverged. <button onClick={() => navigate("/decide")} className="text-path-risk underline cursor-pointer">Start over</button></p>
      </div>
    );
  }

  // For step indicator, include streaming round if it hasn't completed yet
  const displayRounds = isCurrentRoundStreaming && !hasCompletedRound
    ? [...transcript, { round_number: stream.streamingRound, round_name: "", round_title: "", alpha: "", beta: "", metrics: null, status: "streaming" as const }]
    : transcript;

  const safeRound = Math.max(1, Math.min(currentRound, Math.max(displayRounds.length, 1)));
  const round = completedRound;
  const roundName = round?.round_name || ROUNDS[safeRound - 1]?.name || `Round ${safeRound}`;
  const roundTitle = round?.round_title || ROUNDS[safeRound - 1]?.title || "";
  const completedRoundsArr = transcript.map((_, i) => i + 1);
  const pathAName = input?.path_a || "Option A";
  const pathBName = input?.path_b || "Option B";

  const safeLabel = pathAName.length > 30 ? pathAName.slice(0, 30) + "\u2026" : pathAName;
  const riskLabel = pathBName.length > 30 ? pathBName.slice(0, 30) + "\u2026" : pathBName;
  const currentMetrics = allMetrics[safeRound - 1];
  const nextRound = transcript[safeRound];
  const nextRoundName = nextRound?.round_name || ROUNDS[safeRound]?.name;
  const activeTabInfo = CHART_TABS.find((t) => t.key === activeChart)!;

  const heading = userName ? `${userName}\u2019s Decision` : "The Debate";

  const isLastAvailableRound = safeRound >= transcript.length;
  const moreRoundsGenerating = isStreaming && !stream.done && isLastAvailableRound && !isCurrentRoundStreaming;
  const canGoVerdict = safeRound >= transcript.length && verdictReady;
  const bothDone = hasCompletedRound || (showAlpha && showBeta && !alphaIsStreaming && !betaIsStreaming && hasStreamingAlpha && hasStreamingBeta);

  return (
    <div className="min-h-screen bg-void px-4 py-8 md:px-8">
      <div className="max-w-3xl mx-auto">

        <p className="text-center text-ivory-faint text-xs font-mono uppercase tracking-widest mb-1">{heading}</p>

        {/* Step indicator */}
        <div className="flex justify-center items-center gap-1 mb-8">
          {displayRounds.map((r, i) => {
            const stepNum = i + 1;
            const isActive = stepNum === safeRound;
            const isPast = stepNum < safeRound;
            const rName = r.round_name || ROUNDS[i]?.name || `R${stepNum}`;
            const shortName = rName.replace("The ", "");
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
                  {shortName || `R${stepNum}`}
                </button>
              </div>
            );
          })}
          {isStreaming && !stream.done && !isCurrentRoundStreaming && (
            <div className="flex items-center gap-1">
              <span className="w-4 md:w-6 h-px bg-surface-light" />
              <span className="text-[10px] font-mono text-ivory-faint/40 animate-pulse">
                {displayRounds.length + 1 <= 5 ? `R${displayRounds.length + 1}\u2026` : "\u2026"}
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
            {(isCurrentRoundStreaming ? showAlpha : visibleMessages >= 1) && (
              <AgentMessage
                agentName={safeLabel}
                message={alphaText}
                variant="safe"
                voiceId={voiceA}
                streaming={alphaIsStreaming}
              />
            )}
            {(isCurrentRoundStreaming ? showBeta : visibleMessages >= 2) && (
              <AgentMessage
                agentName={riskLabel}
                message={betaText}
                variant="risk"
                voiceId={voiceB}
                streaming={betaIsStreaming}
              />
            )}
          </motion.div>
        </AnimatePresence>

        {/* Skip button (only for non-streaming completed rounds) */}
        {!isCurrentRoundStreaming && visibleMessages < 2 && !skipped && transcript.length > 0 && (
          <div className="mt-4 text-center">
            <button onClick={revealAll} className="text-ivory-faint text-xs font-mono hover:text-ivory-dim transition-colors cursor-pointer">
              Skip &rarr;
            </button>
          </div>
        )}

        {/* Streaming indicator */}
        {isCurrentRoundStreaming && (alphaIsStreaming || betaIsStreaming) && (
          <div className="mt-4 text-center">
            <p className="text-ivory-faint text-xs font-mono animate-pulse">
              {alphaIsStreaming ? `${safeLabel} is arguing\u2026` : `${riskLabel} is responding\u2026`}
            </p>
          </div>
        )}

        {/* User interjection input — shown between rounds when streaming */}
        {isStreaming && !stream.done && bothDone && !alphaIsStreaming && !betaIsStreaming && hasCompletedRound && safeRound < 5 && !interjectionSent[safeRound] && (
          <div className="mt-6">
            <div className="max-w-md mx-auto">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={interjectionText}
                  onChange={(e) => setInterjectionText(e.target.value)}
                  placeholder="Something the agents should consider?"
                  maxLength={500}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && interjectionText.trim()) {
                      const debateId = stream.debateId;
                      if (debateId) {
                        sendInterjection(debateId, interjectionText.trim()).catch(() => {});
                        addInterjection(safeRound, interjectionText.trim());
                      }
                      setInterjectionSent((prev) => ({ ...prev, [safeRound]: true }));
                      setInterjectionText("");
                    }
                  }}
                  className="flex-1 bg-surface border border-surface-light rounded-lg px-4 py-2.5 text-ivory text-sm focus:border-ivory-dim focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                />
                <button
                  onClick={() => {
                    if (!interjectionText.trim()) return;
                    const debateId = stream.debateId;
                    if (debateId) {
                      sendInterjection(debateId, interjectionText.trim()).catch(() => {});
                      addInterjection(safeRound, interjectionText.trim());
                    }
                    setInterjectionSent((prev) => ({ ...prev, [safeRound]: true }));
                    setInterjectionText("");
                  }}
                  disabled={!interjectionText.trim()}
                  className="px-4 py-2.5 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer transition-colors duration-200 hover:border-ivory-dim hover:text-ivory disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline-none"
                >
                  Interject
                </button>
              </div>
              <p className="text-ivory-faint/40 text-[10px] text-center mt-1.5">Optional — redirect the next round</p>
            </div>
          </div>
        )}

        {/* Show submitted interjection */}
        {interjectionSent[safeRound] && stream.interjections[safeRound] && (
          <div className="mt-4 flex justify-center">
            <div className="bg-surface/50 border border-surface-light rounded-lg px-4 py-2.5 max-w-md">
              <p className="text-ivory-faint text-xs font-mono mb-1">You interjected:</p>
              <p className="text-ivory text-sm italic">&ldquo;{stream.interjections[safeRound]}&rdquo;</p>
            </div>
          </div>
        )}

        {/* Next / Generating / Verdict button */}
        {(isCurrentRoundStreaming ? bothDone : visibleMessages >= 2) && !alphaIsStreaming && !betaIsStreaming && (
          <div className="mt-8 text-center">
            {moreRoundsGenerating ? (
              <p className="text-ivory-faint text-xs font-mono animate-pulse">Generating next round&hellip;</p>
            ) : canGoVerdict ? (
              <button onClick={() => navigate("/verdict", { state: { debate, input } })} className="px-8 py-3 rounded-lg text-sm bg-path-risk text-void font-medium transition-[opacity,box-shadow] duration-200 cursor-pointer hover:shadow-[0_0_20px_rgba(212,168,67,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-risk focus-visible:ring-offset-2 focus-visible:ring-offset-void">See the Verdict</button>
            ) : safeRound < transcript.length ? (
              <button onClick={() => setCurrentRound((p) => p + 1)} className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim hover:border-path-risk hover:text-ivory transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk">
                {nextRoundName ? `Next: ${nextRoundName}` : "Next round"} &rarr;
              </button>
            ) : !verdictReady && isStreaming && !stream.done ? (
              <p className="text-ivory-faint text-xs font-mono animate-pulse">
                {stream.streamingAgent === "verdict" ? "The verdict is being written\u2026" : "Generating verdict\u2026"}
              </p>
            ) : null}
          </div>
        )}

        {/* Charts */}
        {(isCurrentRoundStreaming ? bothDone : visibleMessages >= 2) && currentMetrics && (
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
                {activeChart === "Sentiment" && <SentimentChart sentiments={transcript.slice(0, safeRound).map((r) => r.sentiment)} pathAName={pathAName} pathBName={pathBName} />}
              </Suspense>
            </div>
          </div>
        )}

        {/* Round navigation */}
        {(isCurrentRoundStreaming ? bothDone : visibleMessages >= 2) && transcript.length > 1 && (
          <div className="mt-8"><RoundNav totalRounds={transcript.length} currentRound={safeRound} completedRounds={completedRoundsArr} onRoundClick={setCurrentRound} /></div>
        )}
      </div>
    </div>
  );
}
