import { motion } from "framer-motion";

interface TimelineRow {
  label: string;
  text: string;
}

interface Props {
  pathAName: string;
  pathBName: string;
  snapshotA: TimelineRow[];
  snapshotB: TimelineRow[];
}

const rowVariants = {
  hidden: { opacity: 0, y: 6 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.08, duration: 0.4 } }),
};

export default function LifeTimeline({ pathAName, pathBName, snapshotA, snapshotB }: Props) {
  if (snapshotA.length === 0 && snapshotB.length === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <TimelineCard name={pathAName} rows={snapshotA} variant="safe" />
      <TimelineCard name={pathBName} rows={snapshotB} variant="risk" />
    </div>
  );
}

function TimelineCard({ name, rows, variant }: { name: string; rows: TimelineRow[]; variant: "safe" | "risk" }) {
  const borderColor = variant === "safe" ? "border-path-safe" : "border-path-risk";
  const accentText = variant === "safe" ? "text-path-safe" : "text-path-risk";
  const dotBg = variant === "safe" ? "bg-path-safe" : "bg-path-risk";

  return (
    <div className={`border-l-2 ${borderColor} pl-5 py-2`}>
      <p className={`${accentText} text-sm font-medium mb-4`}>
        {name.length > 28 ? name.slice(0, 28) + "\u2026" : name}
      </p>
      <div className="space-y-4">
        {rows.map((row, i) => (
          <motion.div
            key={row.label}
            custom={i}
            initial="hidden"
            animate="visible"
            variants={rowVariants}
            className="flex gap-3 items-start"
          >
            <div className="shrink-0 mt-1.5 flex flex-col items-center">
              <div className={`w-1.5 h-1.5 rounded-full ${dotBg} opacity-60`} />
              {i < rows.length - 1 && <div className="w-px h-5 bg-surface-light mt-1" />}
            </div>
            <div>
              <p className="text-ivory-faint text-[11px] font-mono uppercase tracking-wider">{row.label}</p>
              <p className="text-ivory text-sm leading-relaxed mt-0.5">{row.text}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
