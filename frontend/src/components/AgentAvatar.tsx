interface Props {
  variant: "safe" | "risk";
  speaking?: boolean;
  size?: number;
}

export default function AgentAvatar({ variant, speaking = false, size = 40 }: Props) {
  const isSafe = variant === "safe";
  const stroke = isSafe ? "#4a6fa5" : "#d4a843";
  const glowColor = isSafe ? "rgba(74,111,165,0.4)" : "rgba(212,168,67,0.4)";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{
        filter: speaking ? `drop-shadow(0 0 8px ${glowColor})` : "none",
        transition: "filter 0.3s ease",
      }}
    >
      {isSafe ? (
        <>
          {/* Defender: grounded, rounded silhouette */}
          <circle cx="20" cy="14" r="6" stroke={stroke} strokeWidth="1.5" fill="none" />
          <path d="M10 36 C10 26 14 22 20 22 C26 22 30 26 30 36" stroke={stroke} strokeWidth="1.5" fill="none" strokeLinecap="round" />
        </>
      ) : (
        <>
          {/* Challenger: angular, leaning forward */}
          <circle cx="22" cy="12" r="5.5" stroke={stroke} strokeWidth="1.5" fill="none" />
          <path d="M8 36 C10 24 16 20 22 18 C28 20 32 26 34 36" stroke={stroke} strokeWidth="1.5" fill="none" strokeLinecap="round" />
          <line x1="22" y1="18" x2="16" y2="28" stroke={stroke} strokeWidth="1" strokeLinecap="round" opacity="0.5" />
        </>
      )}

      {speaking && (
        <>
          <circle cx="20" cy="20" r="18" stroke={stroke} strokeWidth="0.5" fill="none" opacity="0.3">
            <animate attributeName="r" values="16;19;16" dur="1.5s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.3;0.1;0.3" dur="1.5s" repeatCount="indefinite" />
          </circle>
        </>
      )}
    </svg>
  );
}
