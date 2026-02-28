import { useState } from "react";
import { motion } from "framer-motion";

interface Props {
  agentName: string;
  message: string;
  variant?: "safe" | "risk";
}

const COLLAPSE_THRESHOLD = 600;

export default function AgentMessage({ agentName, message, variant = "safe" }: Props) {
  const isSafe = variant === "safe";
  const accentColor = isSafe ? "text-path-safe" : "text-path-risk";
  const borderColor = isSafe ? "border-path-safe" : "border-path-risk";
  const dotBg = isSafe ? "bg-path-safe" : "bg-path-risk";
  const paragraphs = message.split("\n\n").filter(Boolean);
  const fullText = paragraphs.join("\n\n");
  const isLong = fullText.length > COLLAPSE_THRESHOLD;
  const [expanded, setExpanded] = useState(false);

  const visibleText = isLong && !expanded ? fullText.slice(0, COLLAPSE_THRESHOLD) : fullText;
  const visibleParagraphs = visibleText.split("\n\n").filter(Boolean);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className={`border-t-[3px] ${borderColor} pt-5`}
    >
      <div className="flex items-center gap-2 mb-4">
        <span className={`w-2.5 h-2.5 rounded-full ${dotBg} shrink-0`} />
        <span className={`${accentColor} text-sm font-medium font-body`}>{agentName}</span>
      </div>
      <div className="text-ivory text-base leading-[1.75] space-y-4">
        {visibleParagraphs.map((paragraph, i) => (
          <p key={i}>
            {i === visibleParagraphs.length - 1 && isLong && !expanded
              ? paragraph + "\u2026"
              : paragraph}
          </p>
        ))}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className={`mt-3 text-xs font-mono ${accentColor} opacity-70 hover:opacity-100 transition-opacity cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk rounded`}
        >
          {expanded ? "Show less" : "Read more"}
        </button>
      )}
    </motion.div>
  );
}
