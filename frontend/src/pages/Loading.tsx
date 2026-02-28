import { useState, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import DarkQuote from "../components/DarkQuote";
import ForkPath from "../components/ForkPath";
import { startDebate } from "../utils/api";
import { storeDebateState, clearDebateState } from "../utils/debateStorage";
import { ROUNDS } from "../utils/constants";
import type { DecisionInput, DebateResponse } from "../types";

export default function Loading() {
  const location = useLocation();
  const navigate = useNavigate();
  const payload = location.state as DecisionInput | null;
  const [currentRound, setCurrentRound] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const hasFired = useRef(false);
  const promiseRef = useRef<Promise<DebateResponse> | null>(null);

  useEffect(() => {
    if (!payload) { navigate("/decide", { replace: true }); return; }

    if (!hasFired.current) {
      hasFired.current = true;
      clearDebateState();
      promiseRef.current = startDebate(payload);
    }

    let active = true;
    const progressTimer = setInterval(() => { setCurrentRound((p) => (p < 5 ? p + 1 : p)); }, 12000);

    promiseRef.current
      ?.then((data) => {
        if (active) {
          clearInterval(progressTimer);
          storeDebateState(data, payload);
          navigate("/debate", { state: { debate: data, input: payload }, replace: true });
        }
      })
      .catch((err) => {
        if (active && err.message !== "Request was cancelled.") {
          clearInterval(progressTimer);
          setError(err.message);
        }
      });

    return () => { active = false; clearInterval(progressTimer); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center px-6 text-center bg-atmosphere">
        <p className="font-display text-lg text-ivory-dim italic relative z-10">&ldquo;The cycle is broken.&rdquo;</p>
        <p className="text-ivory text-sm mt-4 relative z-10">Something went wrong.</p>
        <p className="text-ivory-faint text-xs mt-1 max-w-sm relative z-10">{error}</p>
        <div className="flex gap-3 mt-6 relative z-10">
          <button onClick={() => { hasFired.current = false; setError(null); setCurrentRound(1); navigate("/loading", { state: payload, replace: true }); }}
            className="px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-colors duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]">Try again</button>
          <button onClick={() => navigate("/decide", { replace: true })}
            className="px-6 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer transition-colors duration-200 hover:border-ivory-dim">Start over</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 relative bg-atmosphere">
      <div className="relative z-10 text-center max-w-md">
        <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8 }} className="font-display text-xl text-ivory leading-relaxed" style={{ fontWeight: 400 }}>
          {payload?.user_name ? `${payload.user_name}, two` : "Two"} versions of your future self are preparing their case.
        </motion.p>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5, duration: 0.6 }} className="text-ivory-dim text-sm mt-3">This takes about a minute.</motion.p>
        <div className="mt-14"><DarkQuote intervalMs={5000} /></div>
        <div className="mt-14 flex flex-col items-center">
          <ForkPath variant="loading" progress={currentRound / 5} />
          <p className="text-ivory-faint text-xs font-mono mt-4">Preparing {ROUNDS[currentRound - 1]?.name || "Round"}&hellip;</p>
        </div>
      </div>
    </div>
  );
}
