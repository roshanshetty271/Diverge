import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface FactRotatorProps {
  intervalMs?: number; // Default: 6000 (6 seconds)
}

const DECISION_FACTS: readonly string[] = [
  "People regret inaction twice as much as action over time.",
  "The 'Paradox of Choice' suggests more options lead to less satisfaction.",
  "Visualizing your future self improves long-term decision making.",
  "Your brain processes narratives 22 times more effectively than data alone.",
  "Most major life pivots happen between the ages of 25 and 45.",
  "Decision fatigue reduces willpower by up to 40% after multiple choices.",
  "The 10-10-10 rule: Consider how you'll feel in 10 minutes, 10 months, and 10 years.",
] as const;

export default function FactRotator({ intervalMs = 6000 }: FactRotatorProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % DECISION_FACTS.length);
    }, intervalMs);

    return () => clearInterval(timer);
  }, [intervalMs]);

  return (
    <div className="mt-20 border-t border-white/10 pt-8 w-full max-w-sm">
      <p className="text-[10px] uppercase tracking-widest text-white/30 mb-3">
        Did you know?
      </p>
      <AnimatePresence mode="wait">
        <motion.p
          key={currentIndex}
          initial={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: prefersReducedMotion ? 1 : 0, y: prefersReducedMotion ? 0 : -10 }}
          transition={{ duration: prefersReducedMotion ? 0 : 0.8 }}
          className="text-sm text-white/50 leading-relaxed"
          style={{ willChange: "opacity, transform" }}
        >
          {DECISION_FACTS[currentIndex]}
        </motion.p>
      </AnimatePresence>
    </div>
  );
}
