import { useState, useCallback, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import AgentAvatar from "./AgentAvatar";
import { speak, stopSpeaking, onSpeakingStopped } from "../utils/tts";

interface Props {
  agentName: string;
  message: string;
  variant?: "safe" | "risk";
  voiceId?: string;
  streaming?: boolean;
}

const CHARS_PER_TICK = 3;
const TICK_MS = 16;

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

export default function AgentMessage({ agentName, message, variant = "safe", voiceId, streaming }: Props) {
  const isSafe = variant === "safe";
  const borderColor = isSafe ? "border-l-path-safe" : "border-r-path-risk";
  const accentText = isSafe ? "text-path-safe" : "text-path-risk";
  const [speaking, setSpeaking] = useState(false);
  const cleaned = cleanSlop(message);

  const [revealedLen, setRevealedLen] = useState(streaming ? 0 : cleaned.length);
  const targetLen = useRef(cleaned.length);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!streaming) {
      setRevealedLen(cleaned.length);
      targetLen.current = cleaned.length;
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
      return;
    }

    targetLen.current = cleaned.length;

    if (!timerRef.current && cleaned.length > 0) {
      timerRef.current = setInterval(() => {
        setRevealedLen((prev) => {
          const next = Math.min(prev + CHARS_PER_TICK, targetLen.current);
          if (next >= targetLen.current && timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          return next;
        });
      }, TICK_MS);
    }

    return () => {
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    };
  }, [streaming, cleaned.length]);

  const displayText = streaming ? cleaned.slice(0, revealedLen) : cleaned;
  const isRevealing = streaming && revealedLen < cleaned.length;

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

  const showCursor = streaming || isRevealing;
  const paragraphs = displayText.split("\n\n").filter(Boolean);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className={`flex ${isSafe ? "justify-start" : "justify-end"}`}
    >
      <div className={`max-w-[85%] md:max-w-[75%] flex ${isSafe ? "flex-row" : "flex-row-reverse"} gap-3 items-start`}>
        <div className="shrink-0 mt-1">
          <AgentAvatar variant={variant} speaking={speaking || showCursor} />
        </div>

        <div>
          <div className={`flex items-center gap-2 mb-1.5 ${isSafe ? "" : "justify-end"}`}>
            <span className={`${accentText} text-xs font-medium font-body`}>{agentName}</span>
            {voiceId && !streaming && (
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

          <div className={`bg-surface rounded-lg p-4 border-l-2 border-r-0 ${isSafe ? borderColor : "border-l-0 border-r-2 border-r-path-risk"}`}>
            <div className="text-ivory text-sm leading-[1.75] space-y-3">
              {paragraphs.length > 0 ? (
                paragraphs.map((paragraph, i) => (
                  <p key={i}>
                    {paragraph}
                    {showCursor && i === paragraphs.length - 1 && (
                      <span className="inline-block w-[2px] h-[1em] bg-current ml-0.5 align-text-bottom animate-pulse" />
                    )}
                  </p>
                ))
              ) : showCursor ? (
                <p><span className="inline-block w-[2px] h-[1em] bg-current align-text-bottom animate-pulse" /></p>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
