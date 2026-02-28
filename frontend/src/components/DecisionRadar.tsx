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

export default function DecisionRadar({ metricsA, metricsB, pathAName = "Option A", pathBName = "Option B" }: Props) {
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
    <ResponsiveContainer width="100%" height={280}>
      <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
        <PolarGrid stroke="#1e1e1e" />
        <PolarAngleAxis dataKey="dimension" tick={{ fill: "#a09a8e", fontSize: 11, fontFamily: "JetBrains Mono" }} />
        <Radar name={labelA} dataKey="pathA" stroke="#4a6fa5" fill="#4a6fa5" fillOpacity={0.15} strokeWidth={1.5} />
        <Radar name={labelB} dataKey="pathB" stroke="#d4a843" fill="#d4a843" fillOpacity={0.15} strokeWidth={1.5} />
        <Legend wrapperStyle={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "#a09a8e" }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
