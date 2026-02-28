import { useState, useCallback, useEffect } from "react";
import { motion } from "framer-motion";
import AgentAvatar from "./AgentAvatar";
import { speak, stopSpeaking, onSpeakingStopped } from "../utils/tts";

interface Props {
  agentName: string;
  message: string;
  variant?: "safe" | "risk";
  voiceId?: string;
}

export default function AgentMessage({ agentName, message, variant = "safe", voiceId }: Props) {
  const isSafe = variant === "safe";
  const borderColor = isSafe ? "border-l-path-safe" : "border-r-path-risk";
  const accentText = isSafe ? "text-path-safe" : "text-path-risk";
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => onSpeakingStopped(() => setSpeaking(false)), []);

  const handleSpeak = useCallback(() => {
    if (speaking) {
      stopSpeaking();
      return;
    }
    if (!voiceId) return;
    speak(message, voiceId, {
      onStart: () => setSpeaking(true),
      onEnd: () => setSpeaking(false),
    });
  }, [speaking, message, voiceId]);

  const paragraphs = message.split("\n\n").filter(Boolean);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className={`flex ${isSafe ? "justify-start" : "justify-end"}`}
    >
      <div className={`max-w-[85%] md:max-w-[75%] flex ${isSafe ? "flex-row" : "flex-row-reverse"} gap-3 items-start`}>
        <div className="shrink-0 mt-1">
          <AgentAvatar variant={variant} speaking={speaking} />
        </div>

        <div>
          <div className={`flex items-center gap-2 mb-1.5 ${isSafe ? "" : "justify-end"}`}>
            <span className={`${accentText} text-xs font-medium font-body`}>{agentName}</span>
            {voiceId && (
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
              {paragraphs.map((paragraph, i) => (
                <p key={i}>{paragraph}</p>
              ))}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
