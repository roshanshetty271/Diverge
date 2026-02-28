import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import { useDivergeAuth } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import { getJournal } from "../utils/api";
import type { JournalEntry } from "../types";

export default function Journal() {
  const navigate = useNavigate();
  const { token } = useDivergeAuth();
  const { toast } = useToast();
  const [debates, setDebates] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) { setLoading(false); return; }

    let cancelled = false;
    getJournal(token)
      .then((result) => {
        if (cancelled) return;
        const entries: JournalEntry[] = (result.items || []).map((item: Record<string, unknown>) => ({
          id: (item.debate_id as string) || String(Math.random()),
          pathA: (item.path_a as string) || "Option A",
          pathB: (item.path_b as string) || "Option B",
          lean: ((item.verdict as string) || "").slice(0, 80) || undefined,
          date: (item.created_at as string) || new Date().toISOString(),
          data: item as unknown as JournalEntry["data"],
          input: (item.input as JournalEntry["input"]) || undefined,
        }));
        setDebates(entries);
      })
      .catch((err) => {
        if (!cancelled) toast("Failed to load journal: " + (err instanceof Error ? err.message : "Unknown error"));
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [token, toast]);

  const isEmpty = debates.length === 0;

  if (loading) {
    return (
      <div className="min-h-screen bg-void flex items-center justify-center">
        <p className="text-ivory-faint text-sm font-mono animate-pulse">Loading your journal...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-void px-6 py-16">
      <div className="max-w-2xl mx-auto">
        <StaggerGroup>
          <StaggerItem>
            <h1 className="font-display text-2xl text-ivory" style={{ fontWeight: 400 }}>Decision Journal</h1>
            <p className="text-ivory-dim text-sm mt-1">Every choice shapes your world.</p>
          </StaggerItem>
          {isEmpty && (
            <StaggerItem className="mt-24 text-center">
              <p className="text-ivory-dim italic text-sm max-w-xs mx-auto leading-relaxed">&ldquo;The spinning wheel turns, round and round in a circle. Each fate tied to the next.&rdquo;</p>
              <p className="text-ivory-faint text-xs mt-6">Your first decision awaits.</p>
              <button onClick={() => navigate("/decide")} className="mt-6 px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-all duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]">Make a decision &rarr;</button>
            </StaggerItem>
          )}
          {!isEmpty && (
            <StaggerItem className="mt-8">
              <div className="flex flex-col">
                {debates.map((d) => (
                  <button key={d.id} onClick={() => navigate("/debate", { state: { debate: d.data, input: d.input } })} className="py-4 border-b border-surface-light text-left transition-colors duration-200 cursor-pointer group">
                    <p className="text-ivory text-sm group-hover:text-path-risk transition-colors duration-200 truncate">{d.pathA} vs. {d.pathB}</p>
                    {d.lean && <p className="text-path-risk text-xs mt-1 truncate">Verdict: {d.lean}{d.lean.length >= 80 ? "..." : ""}</p>}
                    <p className="text-ivory-faint/50 text-xs font-mono mt-1">{new Date(d.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</p>
                  </button>
                ))}
              </div>
            </StaggerItem>
          )}
        </StaggerGroup>
      </div>
    </div>
  );
}
