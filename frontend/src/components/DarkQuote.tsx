import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DARK_QUOTES } from "../utils/constants";

interface Props {
  intervalMs?: number;
}

export default function DarkQuote({ intervalMs = 5000 }: Props) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((prev) => (prev + 1) % DARK_QUOTES.length);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);

  const quote = DARK_QUOTES[index];

  return (
    <div className="h-20 flex items-center justify-center">
      <AnimatePresence mode="wait">
        <motion.div key={index} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.8 }} className="text-center">
          <p className="text-ivory-dim italic text-sm max-w-sm mx-auto leading-relaxed">&ldquo;{quote.text}&rdquo;</p>
          <p className="text-ivory-faint text-xs mt-1.5">&mdash; {quote.source}</p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
