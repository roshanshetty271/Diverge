import { AreaChart, Area, XAxis, YAxis, ResponsiveContainer, Tooltip, Legend } from "recharts";
import type { RoundMetrics } from "../types";

interface Props {
  allMetrics: (RoundMetrics | null)[];
  pathAName?: string;
  pathBName?: string;
}

function truncate(s: string, max = 20) {
  return s.length > max ? s.slice(0, max) + "\u2026" : s;
}

export default function TimelineChart({ allMetrics, pathAName = "Option A", pathBName = "Option B" }: Props) {
  const labelA = truncate(pathAName);
  const labelB = truncate(pathBName);
  const valid = (allMetrics || []).filter(Boolean) as RoundMetrics[];
  const data = valid.map((m, i) => ({
    round: `R${i + 1}`,
    pathA: m.path_a?.happiness_estimate ?? 5,
    pathB: m.path_b?.happiness_estimate ?? 5,
  }));

  if (data.length === 0) return <div className="h-[280px] flex items-center justify-center text-ivory-faint text-sm font-mono">Waiting for data&hellip;</div>;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <XAxis dataKey="round" tick={{ fill: "#a09a8e", fontSize: 11, fontFamily: "JetBrains Mono" }} axisLine={{ stroke: "#1e1e1e" }} tickLine={false} />
        <YAxis domain={[0, 10]} tick={{ fill: "#a09a8e", fontSize: 11, fontFamily: "JetBrains Mono" }} axisLine={false} tickLine={false} label={{ value: "Happiness (1\u201310)", angle: -90, position: "insideLeft", style: { fill: "#706b62", fontSize: 10, fontFamily: "JetBrains Mono" }, offset: 10 }} />
        <Tooltip contentStyle={{ background: "#141414", border: "1px solid #1e1e1e", borderRadius: 8, fontSize: 12, fontFamily: "JetBrains Mono", color: "#f0ece2" }} />
        <Area type="monotone" dataKey="pathA" name={labelA} stroke="#4a6fa5" fill="#4a6fa5" fillOpacity={0.1} strokeWidth={1.5} />
        <Area type="monotone" dataKey="pathB" name={labelB} stroke="#d4a843" fill="#d4a843" fillOpacity={0.1} strokeWidth={1.5} />
        <Legend wrapperStyle={{ fontSize: 11, fontFamily: "JetBrains Mono", color: "#a09a8e" }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
