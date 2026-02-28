import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

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

  const textBoxW = 210;
  const textBoxH = 90;
  const textGap = 22;

  const spreadX = 160;
  const sideSpace = textBoxW + textGap + 10;
  const W = sideSpace + spreadX + 120 + spreadX + sideSpace;
  const centerX = W / 2;
  const leftX = centerX - spreadX;
  const rightX = centerX + spreadX;

  const topY = 40;
  const forkY = 80;
  const labelGap = 50;
  const firstNodeY = forkY + labelGap + 40;
  const stepY = 100;
  const totalH = firstNodeY + maxRows * stepY + textBoxH / 2 + 20;

  const pathACurve = `M ${centerX} ${topY} L ${centerX} ${forkY} C ${centerX} ${forkY + 40}, ${leftX} ${forkY + 10}, ${leftX} ${forkY + labelGap}`;
  const pathBCurve = `M ${centerX} ${topY} L ${centerX} ${forkY} C ${centerX} ${forkY + 40}, ${rightX} ${forkY + 10}, ${rightX} ${forkY + labelGap}`;
  const pathALine = `M ${leftX} ${forkY + labelGap} L ${leftX} ${firstNodeY + (maxRows - 1) * stepY}`;
  const pathBLine = `M ${rightX} ${forkY + labelGap} L ${rightX} ${firstNodeY + (maxRows - 1) * stepY}`;

  const toggle = (key: string) => setExpandedNode((prev) => (prev === key ? null : key));

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${totalH}`}
        className="w-full mx-auto"
        style={{ minWidth: 360 }}
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

        {/* Path A curve (left, blue) */}
        <motion.path d={pathACurve} fill="none" stroke="#4a6fa5" strokeWidth={2}
          variants={PATH_DRAW} initial="hidden" animate="visible" />
        <motion.path d={pathALine} fill="none" stroke="#4a6fa5" strokeWidth={2} strokeDasharray="4 4"
          variants={PATH_DRAW} initial="hidden" animate="visible"
          transition={{ delay: 0.5, duration: 1.5 }} />

        {/* Path B curve (right, gold) */}
        <motion.path d={pathBCurve} fill="none" stroke="#d4a843" strokeWidth={2}
          variants={PATH_DRAW} initial="hidden" animate="visible" />
        <motion.path d={pathBLine} fill="none" stroke="#d4a843" strokeWidth={2} strokeDasharray="4 4"
          variants={PATH_DRAW} initial="hidden" animate="visible"
          transition={{ delay: 0.5, duration: 1.5 }} />

        {/* Path labels - positioned to the outer side, below the curve end */}
        <motion.text
          x={leftX - 16} y={forkY + labelGap + 14}
          textAnchor="end"
          className="fill-[#4a6fa5] text-[12px] font-medium"
          variants={LABEL_APPEAR(0.6)}
          initial="hidden" animate="visible"
        >
          {pathAName.length > 24 ? pathAName.slice(0, 24) + "\u2026" : pathAName}
        </motion.text>
        <motion.text
          x={rightX + 16} y={forkY + labelGap + 14}
          textAnchor="start"
          className="fill-[#d4a843] text-[12px] font-medium"
          variants={LABEL_APPEAR(0.6)}
          initial="hidden" animate="visible"
        >
          {pathBName.length > 24 ? pathBName.slice(0, 24) + "\u2026" : pathBName}
        </motion.text>

        {/* Milestone rows */}
        {Array.from({ length: maxRows }).map((_, i) => {
          const y = firstNodeY + i * stepY;
          const delay = 0.8 + i * 0.3;
          const milestone = MILESTONES[i] || `Year ${(i + 1) * 2}`;
          const snapA = snapshotA[i] || null;
          const snapB = snapshotB[i] || null;
          const keyA = `a-${i}`;
          const keyB = `b-${i}`;
          const isExpandedA = expandedNode === keyA;
          const isExpandedB = expandedNode === keyB;

          return (
            <g key={i}>
              {/* Milestone label in center */}
              <motion.text
                x={centerX} y={y + 4}
                textAnchor="middle"
                className="fill-ivory-faint text-[10px] font-mono uppercase tracking-wider"
                variants={LABEL_APPEAR(delay)}
                initial="hidden" animate="visible"
              >
                {milestone}
              </motion.text>

              {/* --- Path A node --- */}
              {snapA && !isExpandedA && (
                <circle cx={leftX} cy={y} r={7} fill="none" stroke="#4a6fa5" strokeWidth={1.5} opacity={0.4}>
                  <animate attributeName="r" values="7;14;7" dur="2.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0;0.5" dur="2.5s" repeatCount="indefinite" />
                </circle>
              )}
              <motion.circle
                cx={leftX} cy={y} r={snapA ? 7 : 4}
                className={snapA ? "fill-[#4a6fa5] cursor-pointer" : "fill-surface-light"}
                variants={NODE_APPEAR(delay)}
                initial="hidden" animate="visible"
                onClick={() => snapA && toggle(keyA)}
                style={isExpandedA ? { filter: "drop-shadow(0 0 6px #4a6fa5)" } : {}}
              />

              {/* Path A text - to the LEFT of the dot */}
              <AnimatePresence>
                {isExpandedA && snapA && (
                  <motion.foreignObject
                    x={leftX - textGap - textBoxW}
                    y={y - textBoxH / 2}
                    width={textBoxW}
                    height={textBoxH}
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    transition={{ duration: 0.25 }}
                  >
                    <div className="h-full flex items-center justify-end">
                      <p className="text-ivory text-xs leading-snug text-right bg-surface/90 border border-[#4a6fa5]/30 rounded-lg px-3 py-2">
                        {snapA.text}
                      </p>
                    </div>
                  </motion.foreignObject>
                )}
              </AnimatePresence>

              {/* --- Path B node --- */}
              {snapB && !isExpandedB && (
                <circle cx={rightX} cy={y} r={7} fill="none" stroke="#d4a843" strokeWidth={1.5} opacity={0.4}>
                  <animate attributeName="r" values="7;14;7" dur="2.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0;0.5" dur="2.5s" repeatCount="indefinite" />
                </circle>
              )}
              <motion.circle
                cx={rightX} cy={y} r={snapB ? 7 : 4}
                className={snapB ? "fill-[#d4a843] cursor-pointer" : "fill-surface-light"}
                variants={NODE_APPEAR(delay)}
                initial="hidden" animate="visible"
                onClick={() => snapB && toggle(keyB)}
                style={isExpandedB ? { filter: "drop-shadow(0 0 6px #d4a843)" } : {}}
              />

              {/* Path B text - to the RIGHT of the dot */}
              <AnimatePresence>
                {isExpandedB && snapB && (
                  <motion.foreignObject
                    x={rightX + textGap}
                    y={y - textBoxH / 2}
                    width={textBoxW}
                    height={textBoxH}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -10 }}
                    transition={{ duration: 0.25 }}
                  >
                    <div className="h-full flex items-center justify-start">
                      <p className="text-ivory text-xs leading-snug text-left bg-surface/90 border border-[#d4a843]/30 rounded-lg px-3 py-2">
                        {snapB.text}
                      </p>
                    </div>
                  </motion.foreignObject>
                )}
              </AnimatePresence>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
