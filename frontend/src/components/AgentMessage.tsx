import { useState, useCallback, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { speak, stopSpeaking, onSpeakingStopped } from "../utils/tts";

interface Props {
  agentName: string;
  message: string;
  variant?: "safe" | "risk";
  voiceId?: string;
  streaming?: boolean;
  instant?: boolean;
  ttsEnabled?: boolean;
  onRevealComplete?: () => void;
}

const SLOP_OPENERS = /^\s*(?:Here's the thing[:\s—–-]*|The (?:uncomfortable |honest |real )?truth is[,:\s—–-]*|Let me be (?:clear|honest|real)[.:\s—–-]*|I'll be honest[,:\s—–-]*|Make no mistake[,:\s—–-]*|Picture this[.:\s—–-]*|Imagine this[.:\s—–-]*|Look[,:\s]+|Listen[,:\s]+)/i;
const SLOP_INLINE = [
  [/\bLet that sink in\.?/gi, ""],
  [/\bFull stop\.?/gi, ""],
  [/\bAt the end of the day[,]?\s*/gi, ""],
  [/\bIt's worth noting\s*(?:that)?\s*/gi, ""],
  [/\bInterestingly,?\s*/gi, ""],
  [/\bCrucially,?\s*/gi, ""],
  [/\bImportantly,?\s*/gi, ""],
] as const;

function cleanSlop(text: string): string {
  let t = text.replace(SLOP_OPENERS, "");
  for (const [pat, rep] of SLOP_INLINE) t = t.replace(pat, rep);
  t = t.replace(/(?<!\w)--(?!\w)/g, " - ");
  t = t.replace(/\u2014/g, " - ").replace(/\u2013/g, " - ");
  return t.replace(/ {2,}/g, " ").trim();
}

function extractParagraphs(text: string): string[] {
  if (!text) return [];
  return text.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
}

export default function AgentMessage({
  agentName,
  message,
  variant = "safe",
  voiceId,
  streaming,
  instant = false,
  ttsEnabled = true,
  onRevealComplete,
}: Props) {
  const isSafe = variant === "safe";
  const accentText = isSafe ? "text-path-safe" : "text-path-risk";
  const [speaking, setSpeaking] = useState(false);
  const cleaned = cleanSlop(message);

  const onRevealCompleteRef = useRef(onRevealComplete);
  onRevealCompleteRef.current = onRevealComplete;
  const hasFiredComplete = useRef(false);
  const bubbleStartedAtRef = useRef(Date.now());

  const incomingParagraphs = extractParagraphs(cleaned);
  const FIRST_MESSAGE_HOLD_MS = 1200;
  const FOLLOWUP_MESSAGE_HOLD_MS = 2300;
  const [revealedCount, setRevealedCount] = useState(instant ? incomingParagraphs.length : 0);

  useEffect(() => {
    if (instant) {
      setRevealedCount(incomingParagraphs.length);
      return;
    }
    if (incomingParagraphs.length <= revealedCount) return;

    const holdMs = revealedCount === 0 ? FIRST_MESSAGE_HOLD_MS : FOLLOWUP_MESSAGE_HOLD_MS;
    const elapsed = Date.now() - bubbleStartedAtRef.current;
    const remaining = Math.max(holdMs - elapsed, 0);
    const t = setTimeout(() => {
      bubbleStartedAtRef.current = Date.now();
      setRevealedCount((prev) => Math.min(prev + 1, incomingParagraphs.length));
    }, remaining);
    return () => clearTimeout(t);
  }, [incomingParagraphs.length, instant, revealedCount]);

  useEffect(() => {
    if (instant) {
      hasFiredComplete.current = false;
      bubbleStartedAtRef.current = Date.now();
      return;
    }
  }, [instant]);

  const visibleParagraphs = instant
    ? incomingParagraphs
    : incomingParagraphs.slice(0, revealedCount);
  const showTypingIndicator = !instant && (revealedCount === 0 || revealedCount < incomingParagraphs.length);

  useEffect(() => {
    hasFiredComplete.current = false;
  }, [agentName]);

  useEffect(() => {
    if (cleaned.length === 0 || streaming || revealedCount < incomingParagraphs.length || hasFiredComplete.current) return;
    hasFiredComplete.current = true;
    const t = setTimeout(() => onRevealCompleteRef.current?.(), 50);
    return () => clearTimeout(t);
  }, [cleaned.length, incomingParagraphs.length, revealedCount, streaming]);

  useEffect(() => onSpeakingStopped(() => setSpeaking(false)), []);

  const handleSpeak = useCallback(() => {
    if (speaking) {
      stopSpeaking();
      return;
    }
    if (!voiceId || streaming) return;
    speak(message, voiceId, {
      onStart: () => setSpeaking(true),
      onEnd: () => setSpeaking(false),
    });
  }, [speaking, message, voiceId, streaming]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className={`flex ${isSafe ? "justify-start" : "justify-end"}`}
    >
      <div className={`max-w-[85%] md:max-w-[75%] relative ${isSafe ? "pl-5" : "pr-5"}`}>
        <div
          className={`absolute top-1 bottom-1 w-[3px] rounded-full ${
            isSafe ? "left-0 bg-path-safe" : "right-0 bg-path-risk"
          }`}
          style={{ opacity: 0.75 }}
        />

        <div className="space-y-3">
          <div className={`flex items-center gap-2 ${isSafe ? "" : "justify-end"}`}>
            <span className={`${accentText} text-xs font-medium font-body tracking-wide uppercase`}>
              {agentName}
            </span>
            {ttsEnabled && voiceId && !streaming && visibleParagraphs.length > 0 && cleaned.length > 0 && (
              <button
                onClick={handleSpeak}
                className={`${accentText} opacity-60 hover:opacity-100 transition-opacity cursor-pointer`}
                aria-label={speaking ? "Stop speaking" : "Listen"}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {speaking ? (
                    <><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></>
                  ) : (
                    <><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.54 8.46a5 5 0 0 1 0 7.07" /><path d="M19.07 4.93a10 10 0 0 1 0 14.14" /></>
                  )}
                </svg>
              </button>
            )}
          </div>

          {visibleParagraphs.map((paragraph, i) => (
            <motion.div
              key={`${agentName}-${i}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              className="bg-surface/70 rounded-md px-4 py-3"
            >
              <p className="text-ivory text-[15px] leading-[1.8]">{paragraph}</p>
            </motion.div>
          ))}

          {showTypingIndicator && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex items-center gap-1.5 px-4 py-2 ${isSafe ? "" : "justify-end"}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${isSafe ? "bg-path-safe" : "bg-path-risk"} animate-pulse`} style={{ animationDelay: "0ms" }} />
              <span className={`w-1.5 h-1.5 rounded-full ${isSafe ? "bg-path-safe" : "bg-path-risk"} animate-pulse`} style={{ animationDelay: "200ms" }} />
              <span className={`w-1.5 h-1.5 rounded-full ${isSafe ? "bg-path-safe" : "bg-path-risk"} animate-pulse`} style={{ animationDelay: "400ms" }} />
            </motion.div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
