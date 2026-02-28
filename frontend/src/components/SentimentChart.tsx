import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from "recharts";
import type { RoundSentiment } from "../types";

interface Props {
  sentiments: (RoundSentiment | null | undefined)[];
  pathAName: string;
  pathBName: string;
}

export default function SentimentChart({ sentiments, pathAName, pathBName }: Props) {
  const data = sentiments
    .map((s, i) => {
      if (!s) return null;
      return {
        round: `R${i + 1}`,
        [`${pathAName} Positive`]: +(s.path_a.positive * 100).toFixed(1),
        [`${pathBName} Positive`]: +(s.path_b.positive * 100).toFixed(1),
        [`${pathAName} Negative`]: +(s.path_a.negative * 100).toFixed(1),
        [`${pathBName} Negative`]: +(s.path_b.negative * 100).toFixed(1),
      };
    })
    .filter(Boolean);

  if (data.length === 0) {
    return (
      <div className="h-[280px] flex items-center justify-center">
        <p className="text-ivory-faint text-sm font-mono">Sentiment analysis not available for this debate.</p>
      </div>
    );
  }

  const safeA = pathAName.length > 15 ? pathAName.slice(0, 15) + "\u2026" : pathAName;
  const safeB = pathBName.length > 15 ? pathBName.slice(0, 15) + "\u2026" : pathBName;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e1e1e" />
        <XAxis dataKey="round" tick={{ fill: "#706b62", fontSize: 11 }} />
        <YAxis tick={{ fill: "#706b62", fontSize: 11 }} domain={[0, 100]} unit="%" />
        <Tooltip
          contentStyle={{ background: "#141414", border: "1px solid #1e1e1e", borderRadius: 8, color: "#f0ece2", fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 11, color: "#a09a8e" }} />
        <Bar dataKey={`${pathAName} Positive`} name={`${safeA} +`} fill="#4a6fa5" radius={[2, 2, 0, 0]} />
        <Bar dataKey={`${pathBName} Positive`} name={`${safeB} +`} fill="#d4a843" radius={[2, 2, 0, 0]} />
        <Bar dataKey={`${pathAName} Negative`} name={`${safeA} -`} fill="#4a6fa580" radius={[2, 2, 0, 0]} />
        <Bar dataKey={`${pathBName} Negative`} name={`${safeB} -`} fill="#d4a84380" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
