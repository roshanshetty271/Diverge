interface Props {
  variant?: "icon" | "loading";
  progress?: number;
  className?: string;
}

export default function ForkPath({ variant = "icon", progress = 1, className = "" }: Props) {
  if (variant === "icon") {
    return (
      <svg viewBox="0 0 24 32" fill="none" className={`w-4 h-5 ${className}`} aria-hidden="true">
        <path d="M12 28 L12 14 L5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M12 14 L19 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  const totalLength = 200;
  const drawn = totalLength * Math.min(1, Math.max(0, progress));

  return (
    <svg viewBox="0 0 80 120" fill="none" className={`w-20 h-30 ${className}`} aria-hidden="true">
      <path
        d="M40 110 L40 55 L18 15"
        stroke="rgba(74,111,165,0.5)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={totalLength}
        strokeDashoffset={totalLength - drawn}
        style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
      />
      <path
        d="M40 55 L62 15"
        stroke="rgba(212,168,67,0.5)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={totalLength}
        strokeDashoffset={Math.max(0, totalLength - (drawn - 70))}
        style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
      />
    </svg>
  );
}
