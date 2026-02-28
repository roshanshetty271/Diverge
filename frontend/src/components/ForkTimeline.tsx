import { useState } from "react";
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

const MILESTONES = ["Year 1", "Year 3", "Year 5", "Year 10", "Deathbed"];

const PATH_DRAW = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: { pathLength: 1, opacity: 1, transition: { duration: 1.8, ease: "easeInOut" } },
};

const NODE_APPEAR = (delay: number) => ({
  hidden: { scale: 0, opacity: 0 },
  visible: { scale: 1, opacity: 1, transition: { delay, duration: 0.4, ease: "backOut" } },
});

const LABEL_APPEAR = (delay: number) => ({
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0, transition: { delay: delay + 0.1, duration: 0.4 } },
});

export default function ForkTimeline({ pathAName, pathBName, snapshotA, snapshotB }: Props) {
  const [expandedNode, setExpandedNode] = useState<string | null>(null);

  if (snapshotA.length < 2 && snapshotB.length < 2) return null;

  const maxRows = Math.max(snapshotA.length, snapshotB.length, 3);

  // SVG dimensions
  const W = 600;
  const topY = 40;
  const forkY = 80;
  const bottomPadding = 30;
  const stepY = 80;
  const totalH = forkY + maxRows * stepY + bottomPadding;
  const centerX = W / 2;
  const spreadX = 160;

  // Build path coordinates: both paths start at center, then diverge
  const leftX = centerX - spreadX;
  const rightX = centerX + spreadX;

  // Bezier curves for the fork
  const pathAPath = `M ${centerX} ${topY} L ${centerX} ${forkY} C ${centerX} ${forkY + 40}, ${leftX} ${forkY + 20}, ${leftX} ${forkY + stepY}`;
  const pathBPath = `M ${centerX} ${topY} L ${centerX} ${forkY} C ${centerX} ${forkY + 40}, ${rightX} ${forkY + 20}, ${rightX} ${forkY + stepY}`;

  // Straight lines after the curve
  const pathALine = `M ${leftX} ${forkY + stepY} L ${leftX} ${forkY + maxRows * stepY}`;
  const pathBLine = `M ${rightX} ${forkY + stepY} L ${rightX} ${forkY + maxRows * stepY}`;

  const getSnapshot = (rows: TimelineRow[], idx: number) => rows[idx] || null;

  const truncName = (n: string) => n.length > 22 ? n.slice(0, 22) + "\u2026" : n;

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${totalH}`}
        className="w-full max-w-[600px] mx-auto"
        style={{ minWidth: 320 }}
      >
        {/* Fork point */}
        <motion.circle
          cx={centerX} cy={topY} r={5}
          className="fill-ivory"
          initial={{ scale: 0 }} animate={{ scale: 1 }}
          transition={{ duration: 0.3 }}
        />
        <motion.text
          x={centerX} y={topY - 14}
          textAnchor="middle"
          className="fill-ivory-faint text-[10px] font-mono uppercase"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          THE FORK
        </motion.text>

        {/* Path A (left, blue) */}
        <motion.path
          d={pathAPath}
          fill="none"
          stroke="#4a6fa5"
          strokeWidth={2}
          variants={PATH_DRAW}
          initial="hidden"
          animate="visible"
        />
        <motion.path
          d={pathALine}
          fill="none"
          stroke="#4a6fa5"
          strokeWidth={2}
          strokeDasharray="4 4"
          variants={PATH_DRAW}
          initial="hidden"
          animate="visible"
          transition={{ delay: 0.5, duration: 1.5 }}
        />

        {/* Path B (right, gold) */}
        <motion.path
          d={pathBPath}
          fill="none"
          stroke="#d4a843"
          strokeWidth={2}
          variants={PATH_DRAW}
          initial="hidden"
          animate="visible"
        />
        <motion.path
          d={pathBLine}
          fill="none"
          stroke="#d4a843"
          strokeWidth={2}
          strokeDasharray="4 4"
          variants={PATH_DRAW}
          initial="hidden"
          animate="visible"
          transition={{ delay: 0.5, duration: 1.5 }}
        />

        {/* Path labels at top */}
        <motion.text
          x={leftX} y={forkY + stepY - 20}
          textAnchor="middle"
          className="fill-[#4a6fa5] text-[11px] font-medium"
          variants={LABEL_APPEAR(0.6)}
          initial="hidden" animate="visible"
        >
          {truncName(pathAName)}
        </motion.text>
        <motion.text
          x={rightX} y={forkY + stepY - 20}
          textAnchor="middle"
          className="fill-[#d4a843] text-[11px] font-medium"
          variants={LABEL_APPEAR(0.6)}
          initial="hidden" animate="visible"
        >
          {truncName(pathBName)}
        </motion.text>

        {/* Milestone nodes */}
        {Array.from({ length: maxRows }).map((_, i) => {
          const y = forkY + (i + 1) * stepY;
          const delay = 0.8 + i * 0.3;
          const milestone = MILESTONES[i] || `Year ${(i + 1) * 2}`;
          const snapA = getSnapshot(snapshotA, i);
          const snapB = getSnapshot(snapshotB, i);
          const nodeKeyA = `a-${i}`;
          const nodeKeyB = `b-${i}`;

          return (
            <g key={i}>
              {/* Milestone label in center */}
              <motion.text
                x={centerX} y={y + 4}
                textAnchor="middle"
                className="fill-ivory-faint text-[9px] font-mono uppercase tracking-wider"
                variants={LABEL_APPEAR(delay)}
                initial="hidden" animate="visible"
              >
                {milestone}
              </motion.text>

              {/* Path A node */}
              <motion.circle
                cx={leftX} cy={y} r={snapA ? 8 : 4}
                className={snapA ? "fill-[#4a6fa5] cursor-pointer" : "fill-surface-light"}
                variants={NODE_APPEAR(delay)}
                initial="hidden" animate="visible"
                onClick={() => snapA && setExpandedNode(expandedNode === nodeKeyA ? null : nodeKeyA)}
                style={snapA ? { filter: expandedNode === nodeKeyA ? "drop-shadow(0 0 6px #4a6fa5)" : "none" } : {}}
              />
              {/* Path A tooltip */}
              {expandedNode === nodeKeyA && snapA && (
                <foreignObject x={leftX - 120} y={y + 14} width={240} height={80}>
                  <div className="bg-surface border border-path-safe rounded-lg p-2.5 text-[11px] text-ivory leading-snug">
                    {snapA.text}
                  </div>
                </foreignObject>
              )}

              {/* Path B node */}
              <motion.circle
                cx={rightX} cy={y} r={snapB ? 8 : 4}
                className={snapB ? "fill-[#d4a843] cursor-pointer" : "fill-surface-light"}
                variants={NODE_APPEAR(delay)}
                initial="hidden" animate="visible"
                onClick={() => snapB && setExpandedNode(expandedNode === nodeKeyB ? null : nodeKeyB)}
                style={snapB ? { filter: expandedNode === nodeKeyB ? "drop-shadow(0 0 6px #d4a843)" : "none" } : {}}
              />
              {/* Path B tooltip */}
              {expandedNode === nodeKeyB && snapB && (
                <foreignObject x={rightX - 120} y={y + 14} width={240} height={80}>
                  <div className="bg-surface border border-path-risk rounded-lg p-2.5 text-[11px] text-ivory leading-snug">
                    {snapB.text}
                  </div>
                </foreignObject>
              )}
            </g>
          );
        })}
      </svg>
      {(snapshotA.length > 0 || snapshotB.length > 0) && (
        <p className="text-ivory-faint/40 text-[10px] text-center mt-2">Click a milestone to see what happens</p>
      )}
    </div>
  );
}
