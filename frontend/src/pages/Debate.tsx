import { useState, useEffect, useCallback, lazy, Suspense } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import AgentMessage from "../components/AgentMessage";
import RoundNav from "../components/RoundNav";
import { useToast } from "../components/Toast";
import { CHECKPOINTED_DEBATE_ENABLED, ROUNDS } from "../utils/constants";
import { loadDebateState, storeDebateState } from "../utils/debateStorage";
import { subscribeDebate, getDebateStream, addInterjection } from "../utils/debateStream";
import { getVoicePair, stopSpeaking } from "../utils/tts";
import { continueCheckpointedDebate, getCapabilities, sendInterjection } from "../utils/api";
import type { Capabilities, DebateResponse, DecisionInput, RoundResult, RoundMetrics } from "../types";

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
  const { toast } = useToast();
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
  const [continuingCheckpointed, setContinuingCheckpointed] = useState(false);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [roundTransition, setRoundTransition] = useState(false);
  const [transitionLabel, setTransitionLabel] = useState({ name: "", title: "" });

  const transcript: RoundResult[] = isStreaming ? stream.rounds : (locationState.debate?.transcript || stored?.debate?.transcript || []);
  const input: DecisionInput | undefined | null = isStreaming ? stream.input : (locationState.input || stored?.input);
  const allMetrics: (RoundMetrics | null)[] = isStreaming ? stream.metrics : (locationState.debate?.metrics || stored?.debate?.metrics || []);
  const verdictReady = isStreaming ? stream.done && !!stream.verdict : true;
  const debate: DebateResponse | undefined = isStreaming
    ? { debate_id: stream.debateId || "", transcript: stream.rounds, verdict: stream.verdict || "", timeline: stream.timeline, metrics: stream.metrics, completed_rounds: stream.completedRounds, total_rounds: stream.totalRounds }
    : (locationState.debate || stored?.debate);
  const isCheckpointedMode = Boolean(
    CHECKPOINTED_DEBATE_ENABLED &&
      !isStreaming &&
      debate &&
      debate.completed_rounds < debate.total_rounds &&
      !debate.verdict,
  );

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

      // Only auto-advance to round 1 when it first starts (not subsequent rounds)
      if (s.streamingRound === 1 && currentRound === 1 && s.rounds.length === 0) {
        setCurrentRound(1);
      }

      if (s.done && s.input && s.rounds.length > 0) {
        storeDebateState(
          { debate_id: s.debateId || "", transcript: s.rounds, verdict: s.verdict || "", timeline: s.timeline, metrics: s.metrics, completed_rounds: s.completedRounds, total_rounds: s.totalRounds },
          s.input,
        );
      }
    });
    return unsub;
  }, [currentRound]);

  const revealAll = useCallback(() => {
    setVisibleMessages(2);
    setSkipped(true);
  }, []);

  const goToRound = useCallback((round: number) => {
    if (round === currentRound) return;
    const name = ROUNDS[round - 1]?.name || `Round ${round}`;
    const title = ROUNDS[round - 1]?.title || "";
    setTransitionLabel({ name, title });
    setRoundTransition(true);
    setTimeout(() => {
      setCurrentRound(round);
      setRoundTransition(false);
    }, 1000);
  }, [currentRound]);

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

  // Always show all rounds in the step indicator from the start
  const totalRoundsToShow = stream.totalRounds || 5;
  const displayRounds = Array.from({ length: totalRoundsToShow }, (_, i) => {
    if (transcript[i]) return transcript[i];
    return { round_number: i + 1, round_name: ROUNDS[i]?.name || `Round ${i + 1}`, round_title: ROUNDS[i]?.title || "", alpha: "", beta: "", metrics: null, status: "pending" as const };
  });

  // The highest round the user can navigate to: completed rounds + the currently streaming round
  const highestAvailableRound = Math.max(transcript.length, stream.streamingRound > 0 ? stream.streamingRound : 0, 1);
  const safeRound = Math.max(1, Math.min(currentRound, highestAvailableRound));
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
  const sentimentAvailable = capabilities?.sentiment ?? transcript.some((entry) => !!entry.sentiment);
  const availableChartTabs = sentimentAvailable ? CHART_TABS : CHART_TABS.filter((tab) => tab.key !== "Sentiment");
  const activeTabInfo = availableChartTabs.find((t) => t.key === activeChart) || availableChartTabs[0];

  useEffect(() => {
    if (!availableChartTabs.some((tab) => tab.key === activeChart)) {
      setActiveChart("Radar");
    }
  }, [activeChart, availableChartTabs]);

  const heading = userName ? `${userName}\u2019s Decision` : "The Debate";

  // Has the user seen all content for this round?
  const bothDone = hasCompletedRound || (showAlpha && showBeta && !alphaIsStreaming && !betaIsStreaming && hasStreamingAlpha && hasStreamingBeta);
  // Is the next round already available (completed or streaming)?
  const nextRoundAvailable = safeRound < transcript.length || (isStreaming && stream.streamingRound > safeRound);
  // Is the next round still being generated (not yet started)?
  const nextRoundGenerating = isStreaming && !stream.done && safeRound >= transcript.length && stream.streamingRound <= safeRound && !isCurrentRoundStreaming;
  const canGoVerdict = safeRound >= transcript.length && verdictReady && !!debate?.verdict;
  const canContinueCheckpointed =
    isCheckpointedMode &&
    safeRound === transcript.length &&
    visibleMessages >= 2 &&
    !continuingCheckpointed;

  const handleCheckpointedContinue = async () => {
    if (!debate || !input || continuingCheckpointed) return;

    setContinuingCheckpointed(true);
    try {
      const result = await continueCheckpointedDebate(
        debate.debate_id,
        interjectionText.trim() || undefined,
      );
      const nextDebate: DebateResponse = {
        debate_id: result.debate_id,
        transcript: result.transcript,
        verdict: result.verdict || "",
        timeline: result.timeline || null,
        metrics: result.metrics,
        completed_rounds: result.completed_rounds,
        total_rounds: result.total_rounds,
        resources: result.resources || [],
      };

      storeDebateState(nextDebate, input);
      setInterjectionText("");
      setCurrentRound(nextDebate.transcript.length);
      navigate("/debate", {
        replace: true,
        state: { debate: nextDebate, input },
      });
    } catch (err) {
      toast(err instanceof Error ? err.message : "Couldn't continue the debate.");
    } finally {
      setContinuingCheckpointed(false);
    }
  };

  return (
    <div className="min-h-screen bg-void px-4 pt-24 pb-8 md:px-8">
      <div className="max-w-4xl mx-auto">

        <p className="text-center text-ivory-faint text-xs font-mono uppercase tracking-widest mb-1">{heading}</p>

        {/* Step indicator — always shows all rounds */}
        <div className="flex justify-center items-center gap-1 mb-8">
          {displayRounds.map((r, i) => {
            const stepNum = i + 1;
            const isActive = stepNum === safeRound;
            const isCompleted = stepNum <= transcript.length;
            const isStreamingNow = isStreaming && stream.streamingRound === stepNum;
            const isReachable = stepNum <= highestAvailableRound;
            const rName = r.round_name || ROUNDS[i]?.name || `R${stepNum}`;
            const shortName = rName.replace("The ", "");
            return (
              <div key={i} className="flex items-center gap-1">
                {i > 0 && <span className={`w-4 md:w-6 h-px ${isCompleted || isActive ? "bg-path-risk" : "bg-surface-light"}`} />}
                <button
                  onClick={() => isReachable && goToRound(stepNum)}
                  className={`text-[10px] md:text-xs font-mono transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk rounded ${
                    isActive
                      ? "text-path-risk font-medium cursor-pointer"
                      : isCompleted
                        ? "text-ivory-dim hover:text-ivory cursor-pointer"
                        : isStreamingNow
                          ? "text-ivory-faint animate-pulse cursor-pointer"
                          : "text-ivory-faint/30 cursor-default"
                  }`}
                >
                  {shortName || `R${stepNum}`}
                </button>
              </div>
            );
          })}
        </div>

        {/* Round header */}
        <div className="text-center mb-8">
          <p className="text-ivory-faint text-xs font-mono uppercase tracking-widest">Round {safeRound} of {stream.totalRounds || 5}</p>
          <h1 className="font-display text-2xl md:text-3xl text-ivory mt-1" style={{ fontWeight: 400 }}>{roundName}</h1>
          <p className="text-ivory-dim text-sm mt-1">{roundTitle}</p>
          {round?.status === "partial" && <p className="text-path-risk text-xs mt-2 font-mono">This round was only partially generated</p>}
        </div>

        {/* Round transition interstitial */}
        <AnimatePresence>
          {roundTransition && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="fixed inset-0 z-50 bg-void flex items-center justify-center"
            >
              <div className="text-center">
                <motion.h2
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15, duration: 0.4 }}
                  className="font-display text-3xl md:text-4xl text-ivory"
                  style={{ fontWeight: 400 }}
                >
                  {transitionLabel.name}
                </motion.h2>
                {transitionLabel.title && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4, duration: 0.4 }}
                    className="text-ivory-faint text-sm mt-2"
                  >
                    {transitionLabel.title}
                  </motion.p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

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
                ttsEnabled={capabilities?.tts ?? false}
              />
            )}
            {(isCurrentRoundStreaming ? showBeta : visibleMessages >= 2) && (
              <AgentMessage
                agentName={riskLabel}
                message={betaText}
                variant="risk"
                voiceId={voiceB}
                streaming={betaIsStreaming}
                ttsEnabled={capabilities?.tts ?? false}
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
              <p className="text-gray-500 text-xs text-center mt-2">Optional &mdash; redirect the next round</p>
            </div>
          </div>
        )}

        {/* Show submitted interjection as a conversation bubble */}
        {interjectionSent[safeRound] && stream.interjections[safeRound] && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: "easeOut" }}
            className="mt-5 flex justify-center"
          >
            <div className="bg-white/5 border border-white/10 rounded-lg px-5 py-3 max-w-md">
              <p className="text-ivory/80 text-sm italic leading-relaxed">&ldquo;{stream.interjections[safeRound]}&rdquo;</p>
              <p className="text-ivory-faint/40 text-[10px] font-mono text-right mt-1">&mdash; You</p>
            </div>
          </motion.div>
        )}

        {isCheckpointedMode && safeRound === transcript.length && visibleMessages >= 2 && (
          <div className="mt-8">
            <div className="max-w-2xl mx-auto">
              <p className="text-gray-400 text-sm text-center mb-3">
                Pause here if you want to add context before the next round.
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={interjectionText}
                  onChange={(e) => setInterjectionText(e.target.value)}
                  placeholder="Something the next round should consider?"
                  maxLength={500}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !continuingCheckpointed) {
                      void handleCheckpointedContinue();
                    }
                  }}
                  className="flex-1 bg-surface border border-surface-light rounded-lg px-4 py-3 text-ivory text-sm focus:border-ivory-dim focus:outline-none placeholder:text-gray-500 transition-colors duration-200"
                />
                <button
                  onClick={() => {
                    void handleCheckpointedContinue();
                  }}
                  disabled={!canContinueCheckpointed}
                  className="px-6 py-3 rounded-lg text-sm border border-path-risk text-path-risk cursor-pointer transition-colors duration-200 hover:bg-path-risk hover:text-void disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none"
                >
                  {continuingCheckpointed ? "Continuing..." : "Continue Debate"}
                </button>
              </div>
              <p className="text-gray-500 text-xs text-center mt-2">
                Optional interjection &mdash; the debate stays paused until you continue.
              </p>
            </div>
          </div>
        )}

        {/* Next / Generating / Verdict button */}
        {(isCurrentRoundStreaming ? bothDone : visibleMessages >= 2) && !alphaIsStreaming && !betaIsStreaming && (
          <div className="mt-8 text-center">
            {canGoVerdict ? (
              <button onClick={() => navigate("/verdict", { state: { debate, input } })} className="px-8 py-3 rounded-lg text-sm bg-path-risk text-void font-medium transition-[opacity,box-shadow] duration-200 cursor-pointer hover:shadow-[0_0_20px_rgba(212,168,67,0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-path-risk focus-visible:ring-offset-2 focus-visible:ring-offset-void">See the Verdict</button>
            ) : nextRoundAvailable ? (
              <button onClick={() => goToRound(safeRound + 1)} className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim hover:border-path-risk hover:text-ivory transition-colors duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk">
                {nextRoundName ? `Next: ${nextRoundName}` : "Next round"} &rarr;
              </button>
            ) : nextRoundGenerating ? (
              <p className="text-ivory-faint text-xs font-mono animate-pulse">Generating next round&hellip;</p>
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
              {availableChartTabs.map((tab) => (
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
                {activeChart === "Sentiment" && sentimentAvailable && <SentimentChart sentiments={transcript.slice(0, safeRound).map((r) => r.sentiment)} pathAName={pathAName} pathBName={pathBName} />}
              </Suspense>
            </div>
          </div>
        )}

        {/* Round navigation */}
        {(isCurrentRoundStreaming ? bothDone : visibleMessages >= 2) && transcript.length > 1 && (
          <div className="mt-8"><RoundNav totalRounds={transcript.length} currentRound={safeRound} completedRounds={completedRoundsArr} onRoundClick={goToRound} /></div>
        )}
      </div>
    </div>
  );
}
