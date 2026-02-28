import { useVoiceInput } from "../hooks/useVoiceInput";

interface Props {
  onResult: (text: string) => void;
  className?: string;
}

export default function VoiceButton({ onResult, className = "" }: Props) {
  const { isListening, isSupported, startListening, stopListening } = useVoiceInput(onResult);

  if (!isSupported) return null;

  return (
    <button
      type="button"
      onClick={isListening ? stopListening : startListening}
      className={`shrink-0 w-10 h-10 rounded-lg border transition-all duration-200 flex items-center justify-center cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk ${
        isListening
          ? "border-path-risk bg-path-risk/10 text-path-risk animate-pulse"
          : "border-surface-light text-ivory-faint hover:border-ivory-dim hover:text-ivory-dim"
      } ${className}`}
      aria-label={isListening ? "Stop listening" : "Voice input"}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {isListening ? (
          <><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></>
        ) : (
          <>
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="22" />
          </>
        )}
      </svg>
    </button>
  );
}
