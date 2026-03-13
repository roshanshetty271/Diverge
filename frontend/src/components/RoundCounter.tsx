import { motion } from "framer-motion";
import { memo } from "react";

interface RoundCounterProps {
  current: number; // 0-5
  total: number; // Always 5
}

function RoundCounter({ current, total }: RoundCounterProps) {
  const displayText = current === 0 
    ? "Initializing Simulation" 
    : `Round ${current} of ${total}`;

  return (
    <span className="text-[10px] uppercase tracking-[0.3em] text-white/40 font-serif">
      {displayText}
    </span>
  );
}

export default memo(RoundCounter);
