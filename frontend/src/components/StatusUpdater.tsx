import { motion } from "framer-motion";
import { memo } from "react";

interface StatusUpdaterProps {
  roundCount: number; // 0-5
  streamingRound: number; // 0-5
  done: boolean;
}

const STATUS_MESSAGES: Record<number, string> = {
  0: "Simulating Year 1: The Ripple...",
  1: "Alpha is building a financial case...",
  2: "Beta is exploring growth potential...",
  3: "Calculating social impact ripple...",
  4: "Finalizing emotional resonance scores...",
  5: "Divergence complete.",
};

function getStatusMessage(roundCount: number, streamingRound: number, done: boolean): string {
  if (done) {
    return STATUS_MESSAGES[5];
  }

  // Use streaming round for more responsive updates
  const index = streamingRound > 0 ? streamingRound : roundCount;
  const clampedIndex = Math.max(0, Math.min(5, index));
  
  return STATUS_MESSAGES[clampedIndex];
}

function StatusUpdater({ roundCount, streamingRound, done }: StatusUpdaterProps) {
  const message = getStatusMessage(roundCount, streamingRound, done);
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <motion.p
      key={message}
      initial={{ opacity: prefersReducedMotion ? 1 : 0.6 }}
      animate={{ opacity: prefersReducedMotion ? 1 : [0.6, 1, 0.6] }}
      transition={{ duration: prefersReducedMotion ? 0 : 2, repeat: prefersReducedMotion ? 0 : Infinity, ease: "easeInOut" }}
      className="text-amber-gold/80 font-serif text-sm tracking-widest uppercase"
      style={{ willChange: "opacity" }}
      aria-live="polite"
      aria-atomic="true"
    >
      {message}
    </motion.p>
  );
}

export default memo(StatusUpdater);
