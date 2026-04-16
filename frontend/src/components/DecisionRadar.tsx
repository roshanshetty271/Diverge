import { useState } from "react";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Legend } from "recharts";
import type { PathMetrics } from "../types";

interface Props {
  metricsA: PathMetrics | null;
  metricsB: PathMetrics | null;
  pathAName?: string;
  pathBName?: string;
}

function truncate(s: string, max = 20) {
  return s.length > max ? s.slice(0, max) + "\u2026" : s;
}

function normalize(m: PathMetrics | null) {
  if (!m) return { financial: 5, happiness: 5, growth: 5, values: 5, lowRegret: 5 };
  return {
    financial: Math.round((m.financial_confidence ?? 0.5) * 10),
    happiness: m.happiness_estimate ?? 5,
    growth: m.growth_potential ?? 5,
    values: m.values_alignment ?? 5,
    lowRegret: Math.round((1 - (m.regret_risk ?? 0.5)) * 10),
  };
}

const METRIC_INFO = [
  { label: "Financial", detail: "confidence inferred from debate arguments" },
  { label: "Happiness", detail: "inferred from debate content" },
  { label: "Growth", detail: "inferred from debate content" },
  { label: "Values", detail: "inferred from debate content" },
  { label: "Low Regret", detail: "inverted regret risk score" },
];

export default function DecisionRadar({ metricsA, metricsB, pathAName = "Option A", pathBName = "Option B" }: Props) {
  const [showMethodology, setShowMethodology] = useState(false);
  const labelA = truncate(pathAName);
  const labelB = truncate(pathBName);
  const a = normalize(metricsA);
  const b = normalize(metricsB);
  const data = [
    { dimension: "Financial", pathA: a.financial, pathB: b.financial },
    { dimension: "Happiness", pathA: a.happiness, pathB: b.happiness },
    { dimension: "Growth", pathA: a.growth, pathB: b.growth },
    { dimension: "Values", pathA: a.values, pathB: b.values },
    { dimension: "Low Regret", pathA: a.lowRegret, pathB: b.lowRegret },
  ];

  return (
    <div>
      <ResponsiveContainer width="100%" height={280}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="#1e1e1e" />
          <PolarAngleAxis dataKey="dimension" tick={{ fill: "#a09a8e", fontSize: 11, fontFamily: "JetBrains Mono" }} />
          <Radar name={labelA} dataKey="pathA" stroke="#4a6fa5" fill="#4a6fa5" fillOpacity={0.15} strokeWidth={1.5} />
          <Radar name={labelB} dataKey="pathB" stroke="#d4a843" fill="#d4a843" fillOpacity={0.15} strokeWidth={1.5} />
          <Legend wrapperStyle={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "#a09a8e" }} />
        </RadarChart>
      </ResponsiveContainer>

      <div className="mt-3 border-t border-white/5 pt-3">
        <button
          onClick={() => setShowMethodology(!showMethodology)}
          className="text-[11px] font-mono text-gray-500 hover:text-gray-300 transition-colors w-full text-center"
        >
          How these numbers work {showMethodology ? "\u25B4" : "\u25BE"}
        </button>
        {showMethodology && (
          <div className="mt-3 space-y-1.5 max-w-xs mx-auto">
            {METRIC_INFO.map((m) => (
              <div key={m.label} className="flex items-baseline gap-2 text-[11px] font-mono">
                <span className="text-gray-400">{"\u25C7"}</span>
                <span className="text-gray-400 min-w-[5rem]">{m.label}</span>
                <span className="text-gray-500">AI Estimate &mdash; {m.detail}</span>
              </div>
            ))}
            <p className="text-[11px] text-gray-500 mt-2 pt-2 border-t border-white/5">
              {"\u25C7"} = AI estimate from debate text. Treat as directional, not precise.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
