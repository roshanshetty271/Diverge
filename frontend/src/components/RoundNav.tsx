import { Check } from "lucide-react";
import { ROUNDS } from "../utils/constants";

interface Props {
  totalRounds?: number;
  currentRound: number;
  completedRounds?: number[];
  onRoundClick: (round: number) => void;
}

export default function RoundNav({ totalRounds = 5, currentRound, completedRounds = [], onRoundClick }: Props) {
  return (
    <div className="flex justify-center gap-2 md:gap-3">
      {Array.from({ length: totalRounds }, (_, i) => {
        const roundNum = i + 1;
        const isCurrent = roundNum === currentRound;
        const isCompleted = completedRounds.includes(roundNum);
        const isFuture = roundNum > currentRound && !isCompleted;
        const roundInfo = ROUNDS[i];
        const shortName = roundInfo?.name.replace("The ", "") || `R${roundNum}`;

        return (
          <button
            key={roundNum}
            onClick={() => (isCompleted || isCurrent) && onRoundClick(roundNum)}
            disabled={isFuture}
            title={roundInfo ? `${roundInfo.name}: ${roundInfo.title}` : `Round ${roundNum}`}
            aria-label={roundInfo ? `${roundInfo.name} - ${roundInfo.title}` : `Round ${roundNum}`}
            className={`flex flex-col items-center gap-1 px-3 py-2 rounded-lg text-xs font-mono transition-colors duration-200 bg-surface focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk ${
              isCurrent
                ? "border border-path-risk text-ivory"
                : isCompleted
                  ? "border border-surface-light text-path-safe cursor-pointer hover:border-path-safe"
                  : "border border-surface-light text-ivory-faint opacity-30 cursor-default"
            }`}
          >
            <span className="text-[10px]">
              {isCompleted && !isCurrent ? <Check size={12} strokeWidth={2} aria-hidden="true" /> : roundNum}
            </span>
            <span className="text-[9px] tracking-wide uppercase hidden md:block">{shortName}</span>
          </button>
        );
      })}
    </div>
  );
}
