import { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import DarkQuote from "../components/DarkQuote";
import ForkPath from "../components/ForkPath";
import { startDebateStream, subscribeDebate, getDebateStream, resetDebateStream } from "../utils/debateStream";
import { ROUNDS } from "../utils/constants";
import type { DecisionInput } from "../types";

export default function Loading() {
  const location = useLocation();
  const navigate = useNavigate();
  const payload = location.state as DecisionInput | null;
  const [roundCount, setRoundCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const hasFired = useRef(false);
  const hasNavigated = useRef(false);

  useEffect(() => {
    if (!payload) { navigate("/decide", { replace: true }); return; }

    if (!hasFired.current) {
      hasFired.current = true;
      resetDebateStream();
      startDebateStream(payload);
    }

    const unsub = subscribeDebate(() => {
      const s = getDebateStream();
      setRoundCount(s.rounds.length);

      if (s.error && !hasNavigated.current) {
        setError(s.error);
        return;
      }

      if (s.rounds.length >= 1 && !hasNavigated.current) {
        hasNavigated.current = true;
        navigate("/debate", { replace: true });
      }
    });

    return unsub;
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

  const roundLabel = roundCount > 0
    ? `Round ${roundCount} ready`
    : `Preparing ${ROUNDS[0]?.name || "Round 1"}\u2026`;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 relative bg-atmosphere">
      <div className="relative z-10 text-center max-w-md">
        <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8 }} className="font-display text-xl text-ivory leading-relaxed" style={{ fontWeight: 400 }}>
          {payload?.user_name ? `${payload.user_name}, two` : "Two"} versions of your future self are preparing their case.
        </motion.p>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 0.6 }} className="text-ivory-dim text-sm mt-3">
          {roundCount > 0 ? "Almost there\u2026" : "This takes about a minute."}
        </motion.p>
        <div className="mt-14"><DarkQuote intervalMs={5000} /></div>
        <div className="mt-14 flex flex-col items-center">
          <ForkPath variant="loading" progress={Math.max(roundCount / 5, 0.05)} />
          <p className="text-ivory-faint text-xs font-mono mt-4">{roundLabel}</p>
        </div>
      </div>
    </div>
  );
}
