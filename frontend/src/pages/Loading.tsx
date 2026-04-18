import { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import AnimatedForkPath from "../components/AnimatedForkPath";
import StatusUpdater from "../components/StatusUpdater";
import RoundCounter from "../components/RoundCounter";
import FactRotator from "../components/FactRotator";
import CancelButton from "../components/CancelButton";
import {
  startDebateStream,
  startCheckpointedStream,
  subscribeDebate,
  getDebateStream,
  resetDebateStream,
} from "../utils/debateStream";
import { calculateProgress } from "../utils/loadingHelpers";
import { CHECKPOINTED_DEBATE_ENABLED } from "../utils/constants";
import type { DecisionInput } from "../types";

interface LoadingRouteState {
  input: DecisionInput;
  captchaToken?: string | null;
}

export default function Loading() {
  const location = useLocation();
  const navigate = useNavigate();
  const routeState = (location.state || null) as DecisionInput | LoadingRouteState | null;
  const payload = routeState && "input" in routeState ? routeState.input : routeState;
  const captchaToken = routeState && "input" in routeState ? routeState.captchaToken ?? null : null;
  const [roundCount, setRoundCount] = useState(0);
  const [streamingRound, setStreamingRound] = useState(0);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasFired = useRef(false);
  const hasNavigated = useRef(false);
  const startedAtRef = useRef<number>(Date.now());
  const MIN_LOADING_MS = 3500;

  const handleCancel = () => {
    resetDebateStream();
    navigate("/decide", { replace: true });
  };

  useEffect(() => {
    if (!payload) { navigate("/decide", { replace: true }); return; }

    if (!hasFired.current) {
      hasFired.current = true;
      startedAtRef.current = Date.now();
      resetDebateStream();
      if (CHECKPOINTED_DEBATE_ENABLED) {
        void startCheckpointedStream(payload, captchaToken);
      } else {
        void startDebateStream(payload, captchaToken);
      }
    }

    const tryNavigate = () => {
      if (hasNavigated.current) return;
      const s = getDebateStream();

      if (s.error) {
        if (s.error === "__crisis__") {
          hasNavigated.current = true;
          navigate("/crisis", { replace: true });
          return;
        }
        setError(s.error);
        return;
      }

      const elapsed = Date.now() - startedAtRef.current;
      const streamStarted = s.streamingRound >= 1 || s.streamingAlphaText.length > 0 || s.rounds.length >= 1;
      // Hold Loading for a minimum display window so the transition doesn't feel abrupt.
      if (elapsed >= MIN_LOADING_MS && streamStarted) {
        hasNavigated.current = true;
        navigate("/debate", { replace: true });
      }
    };

    const unsub = subscribeDebate(() => {
      const s = getDebateStream();
      setRoundCount(s.rounds.length);
      setStreamingRound(s.streamingRound || 0);
      setDone(s.done || false);
      tryNavigate();
    });

    // Also tick in case the stream is already ahead when the min-hold elapses.
    const interval = setInterval(tryNavigate, 250);

    return () => {
      unsub();
      clearInterval(interval);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 text-center bg-atmosphere">
        <p className="font-display text-lg text-ivory-dim italic relative z-10">&ldquo;The cycle is broken.&rdquo;</p>
        <p className="text-ivory text-sm mt-4 relative z-10">Something went wrong.</p>
        <p className="text-ivory-faint text-xs mt-1 max-w-sm relative z-10">{error}</p>
        <div className="flex gap-3 mt-6 relative z-10">
          <button onClick={() => { hasFired.current = false; hasNavigated.current = false; setError(null); setRoundCount(0); }}
            className="px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-colors duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]">Try again</button>
          <button onClick={() => navigate("/decide", { replace: true })}
            className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer transition-colors duration-200 hover:border-ivory-dim">Start over</button>
        </div>
      </div>
    );
  }

  const progress = calculateProgress(roundCount, 5);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12 relative overflow-hidden" style={{ backgroundColor: "#0a0a0a" }}>
      {/* Ambient Background Effects */}
      <div className="fixed inset-0 z-0">
        {/* Film grain overlay */}
        <div 
          className="absolute inset-0 opacity-[0.05] pointer-events-none"
          style={{
            backgroundImage: "url('data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E')",
            backgroundRepeat: "repeat",
          }}
        />
        {/* Gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-void-black to-void-black"></div>
        {/* Subtle radial glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-diverge-blue/5 rounded-full blur-[120px]"></div>
      </div>

      {/* Main Content */}
      <main className="relative z-10 w-full max-w-2xl flex flex-col items-center text-center">
        {/* Animated Fork Path with Round Counter */}
        <div className="mb-12 relative h-48 w-64">
          <AnimatedForkPath progress={progress} />
          {/* Round Counter positioned below fork */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 mt-16">
            <RoundCounter current={roundCount} total={5} />
          </div>
        </div>

        {/* Narrative Text */}
        <div className="space-y-6">
          <motion.h1 
            initial={{ opacity: 0, y: 8 }} 
            animate={{ opacity: 1, y: 0 }} 
            transition={{ duration: 0.8 }}
            className="font-serif text-2xl md:text-3xl text-white tracking-wide leading-relaxed"
          >
            <span className="text-amber-gold">{payload?.user_name || "Alex"}</span>, two versions of your future self are preparing their case.
          </motion.h1>
          
          <motion.p 
            initial={{ opacity: 0 }} 
            animate={{ opacity: 1 }} 
            transition={{ delay: 0.5, duration: 0.6 }}
            className="text-white/60 text-sm md:text-base max-w-md mx-auto leading-relaxed italic"
          >
            This takes about a minute.
          </motion.p>

          {/* Status Updates */}
          <div className="h-8 overflow-hidden">
            <StatusUpdater 
              roundCount={roundCount} 
              streamingRound={streamingRound} 
              done={done} 
            />
          </div>
        </div>

        {/* Rotating Facts */}
        <FactRotator intervalMs={6000} />
      </main>

      {/* Cancel Button */}
      <footer className="fixed bottom-8 w-full px-8 flex justify-end z-20">
        <CancelButton onCancel={handleCancel} />
      </footer>
    </div>
  );
}
