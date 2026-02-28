import { useState, useEffect, lazy, Suspense } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import AgentMessage from "../components/AgentMessage";
import { getSharedDebate } from "../utils/api";
import { ROUNDS } from "../utils/constants";
import type { RoundResult, RoundMetrics } from "../types";

const DecisionRadar = lazy(() => import("../components/DecisionRadar"));

export default function SharedDebate() {
  const { shareId } = useParams<{ shareId: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [currentRound, setCurrentRound] = useState(1);

  useEffect(() => {
    if (!shareId) return;
    getSharedDebate(shareId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [shareId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-void flex items-center justify-center">
        <p className="text-ivory-faint text-sm font-mono animate-pulse">Loading shared debate...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-void flex flex-col items-center justify-center gap-4">
        <p className="text-ivory-dim text-sm">{error || "Debate not found."}</p>
        <button onClick={() => navigate("/")} className="text-path-risk text-sm underline cursor-pointer">Go to Diverge</button>
      </div>
    );
  }

  const transcript = (data.transcript as RoundResult[]) || [];
  const metrics = (data.metrics as (RoundMetrics | null)[]) || [];
  const verdict = (data.verdict as string) || "";
  const inputData = (data.input as Record<string, string>) || {};
  const pathAName = inputData.path_a || (data.path_a as string) || "Option A";
  const pathBName = inputData.path_b || (data.path_b as string) || "Option B";
  const safeLabel = pathAName.length > 30 ? pathAName.slice(0, 30) + "\u2026" : pathAName;
  const riskLabel = pathBName.length > 30 ? pathBName.slice(0, 30) + "\u2026" : pathBName;

  const safeRound = Math.max(1, Math.min(currentRound, transcript.length));
  const round = transcript[safeRound - 1];
  const roundName = round?.round_name || ROUNDS[safeRound - 1]?.name || `Round ${safeRound}`;
  const roundTitle = round?.round_title || ROUNDS[safeRound - 1]?.title || "";
  const currentMetrics = metrics[safeRound - 1];

  const verdictLines = verdict
    .replace(/\*\*/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .split("\n\n")
    .filter((l) => l.trim().length > 5);

  return (
    <div className="min-h-screen bg-void px-4 py-8 md:px-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-2">
          <p className="text-ivory-faint text-[10px] font-mono uppercase tracking-[0.3em]">Shared Debate</p>
          <h1 className="font-display text-xl md:text-2xl text-ivory mt-1" style={{ fontWeight: 400 }}>
            {pathAName} <span className="text-ivory-faint">vs.</span> {pathBName}
          </h1>
        </div>

        {/* Round tabs */}
        <div className="flex justify-center items-center gap-1 my-8">
          {transcript.map((r, i) => {
            const stepNum = i + 1;
            const isActive = stepNum === safeRound;
            const isPast = stepNum < safeRound;
            const shortName = (r.round_name || ROUNDS[i]?.name || `R${stepNum}`).replace("The ", "");
            return (
              <div key={i} className="flex items-center gap-1">
                {i > 0 && <span className={`w-4 md:w-6 h-px ${isPast || isActive ? "bg-path-risk" : "bg-surface-light"}`} />}
                <button
                  onClick={() => setCurrentRound(stepNum)}
                  className={`text-[10px] md:text-xs font-mono transition-colors cursor-pointer focus-visible:outline-none rounded ${
                    isActive ? "text-path-risk font-medium" : isPast ? "text-ivory-dim hover:text-ivory" : "text-ivory-faint/40"
                  }`}
                >
                  {shortName}
                </button>
              </div>
            );
          })}
        </div>

        {/* Round header */}
        <div className="text-center mb-8">
          <p className="text-ivory-faint text-xs font-mono uppercase tracking-widest">Round {safeRound} of {transcript.length}</p>
          <h2 className="font-display text-2xl text-ivory mt-1" style={{ fontWeight: 400 }}>{roundName}</h2>
          <p className="text-ivory-dim text-sm mt-1">{roundTitle}</p>
        </div>

        {/* Messages */}
        <motion.div key={safeRound} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }} className="space-y-5">
          {round?.alpha && <AgentMessage agentName={safeLabel} message={round.alpha} variant="safe" />}
          {round?.beta && <AgentMessage agentName={riskLabel} message={round.beta} variant="risk" />}
        </motion.div>

        {/* Chart */}
        {currentMetrics && (
          <div className="mt-10">
            <div className="bg-surface rounded-lg border border-surface-light p-4 md:p-6">
              <Suspense fallback={<div className="h-[280px] flex items-center justify-center text-ivory-faint text-sm font-mono">Loading chart&hellip;</div>}>
                <DecisionRadar metricsA={currentMetrics?.path_a || null} metricsB={currentMetrics?.path_b || null} pathAName={pathAName} pathBName={pathBName} />
              </Suspense>
            </div>
          </div>
        )}

        {/* Navigation */}
        <div className="mt-8 flex justify-center gap-3">
          {safeRound > 1 && (
            <button onClick={() => setCurrentRound((p) => p - 1)} className="px-4 py-2 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer hover:border-ivory-dim transition-colors">&larr; Previous</button>
          )}
          {safeRound < transcript.length && (
            <button onClick={() => setCurrentRound((p) => p + 1)} className="px-4 py-2 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer hover:border-path-risk hover:text-ivory transition-colors">Next &rarr;</button>
          )}
        </div>

        {/* Verdict section */}
        {verdict && safeRound === transcript.length && (
          <div className="mt-12">
            <div className="w-16 h-px bg-path-risk mx-auto" />
            <p className="text-ivory-faint text-xs font-mono uppercase tracking-[0.25em] mt-4 text-center">The Verdict</p>
            <div className="mt-6 space-y-4">
              {verdictLines.slice(0, 6).map((line, i) => (
                <p key={i} className="text-ivory text-sm leading-[1.75]">{line.trim()}</p>
              ))}
            </div>
          </div>
        )}

        {/* CTA */}
        <div className="mt-16 text-center">
          <p className="text-ivory-faint text-xs mb-3">Have a decision of your own?</p>
          <button onClick={() => navigate("/decide")} className="px-8 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-all duration-200 hover:shadow-[0_0_20px_rgba(212,168,67,0.12)]">
            Make your own decision &rarr;
          </button>
          <p className="font-display text-sm text-ivory-dim italic mt-8">Sic Mundus Creatus Est.</p>
        </div>
      </div>
    </div>
  );
}
