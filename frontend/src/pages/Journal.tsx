import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import { useDivergeAuth } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import { getJournal, reflectOnDebate } from "../utils/api";
import type { JournalEntry } from "../types";

interface ExtendedEntry extends JournalEntry {
  chosen_path?: string;
  satisfaction_rating?: number;
  reflection_note?: string;
}

export default function Journal() {
  const navigate = useNavigate();
  const { token } = useDivergeAuth();
  const { toast } = useToast();
  const [debates, setDebates] = useState<ExtendedEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [reflectingId, setReflectingId] = useState<string | null>(null);
  const [reflectSatisfaction, setReflectSatisfaction] = useState(5);
  const [reflectNote, setReflectNote] = useState("");

  useEffect(() => {
    if (!token) { setLoading(false); return; }

    let cancelled = false;
    getJournal(token)
      .then((result) => {
        if (cancelled) return;
        const entries: ExtendedEntry[] = (result.items || []).map((item: Record<string, unknown>) => ({
          id: (item.debate_id as string) || String(Math.random()),
          pathA: (item.path_a as string) || "Option A",
          pathB: (item.path_b as string) || "Option B",
          lean: ((item.verdict as string) || "").slice(0, 80) || undefined,
          date: (item.created_at as string) || new Date().toISOString(),
          data: item as unknown as JournalEntry["data"],
          input: (item.input as JournalEntry["input"]) || undefined,
          chosen_path: (item.chosen_path as string) || undefined,
          satisfaction_rating: (item.satisfaction_rating as number) || undefined,
          reflection_note: (item.reflection_note as string) || undefined,
        }));
        setDebates(entries);
      })
      .catch((err) => {
        if (!cancelled) toast("Failed to load journal: " + (err instanceof Error ? err.message : "Unknown error"));
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [token, toast]);

  const handleReflect = async (debateId: string) => {
    if (!token) return;
    try {
      await reflectOnDebate(debateId, reflectSatisfaction, reflectNote, token);
      setDebates((prev) =>
        prev.map((d) =>
          d.id === debateId
            ? { ...d, satisfaction_rating: reflectSatisfaction, reflection_note: reflectNote }
            : d,
        ),
      );
      setReflectingId(null);
      setReflectNote("");
      setReflectSatisfaction(5);
      toast("Reflection saved.");
    } catch {
      toast("Couldn\u2019t save reflection. Try again.");
    }
  };

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
                  <div key={d.id} className="py-4 border-b border-surface-light">
                    <button
                      onClick={() => navigate("/debate", { state: { debate: d.data, input: d.input } })}
                      className="w-full text-left transition-colors duration-200 cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <p className="text-ivory text-sm group-hover:text-path-risk transition-colors duration-200 truncate flex-1">{d.pathA} vs. {d.pathB}</p>
                        {d.chosen_path && (
                          <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                            d.chosen_path === d.pathA ? "border-path-safe text-path-safe" : "border-path-risk text-path-risk"
                          }`}>
                            Chose: {d.chosen_path.length > 18 ? d.chosen_path.slice(0, 18) + "\u2026" : d.chosen_path}
                          </span>
                        )}
                      </div>
                      {d.lean && <p className="text-path-risk text-xs mt-1 truncate">Verdict: {d.lean}{d.lean.length >= 80 ? "..." : ""}</p>}
                      <p className="text-ivory-faint/50 text-xs font-mono mt-1">{new Date(d.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</p>
                    </button>

                    {/* Reflection display */}
                    {d.satisfaction_rating && (
                      <div className="mt-2 ml-1 flex items-center gap-2 text-xs text-ivory-dim">
                        <span className="font-mono">Satisfaction: {d.satisfaction_rating}/10</span>
                        {d.reflection_note && <span className="italic truncate max-w-[200px]">&ldquo;{d.reflection_note}&rdquo;</span>}
                      </div>
                    )}

                    {/* Reflect button */}
                    {d.chosen_path && !d.satisfaction_rating && (
                      <button
                        onClick={() => setReflectingId(d.id)}
                        className="mt-2 text-xs text-ivory-faint hover:text-ivory transition-colors cursor-pointer"
                      >
                        Reflect on this decision &rarr;
                      </button>
                    )}

                    {/* Reflect modal */}
                    {reflectingId === d.id && (
                      <div className="mt-3 bg-surface rounded-lg border border-surface-light p-4">
                        <p className="text-ivory text-sm mb-3">How satisfied are you with this choice?</p>
                        <div className="flex items-center gap-3 mb-3">
                          <input
                            type="range"
                            min={1} max={10}
                            value={reflectSatisfaction}
                            onChange={(e) => setReflectSatisfaction(parseInt(e.target.value, 10))}
                            className="flex-1 accent-path-risk"
                          />
                          <span className="text-ivory font-mono text-sm w-8 text-center">{reflectSatisfaction}</span>
                        </div>
                        <textarea
                          value={reflectNote}
                          onChange={(e) => setReflectNote(e.target.value.slice(0, 1000))}
                          placeholder="Any thoughts on how it went? (optional)"
                          rows={2}
                          className="w-full bg-void border border-surface-light rounded-lg p-3 text-ivory text-sm resize-none focus:border-ivory-dim focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                        />
                        <div className="flex gap-2 mt-3">
                          <button onClick={() => handleReflect(d.id)} className="px-4 py-2 rounded-lg text-sm bg-path-risk text-void font-medium cursor-pointer">Save Reflection</button>
                          <button onClick={() => setReflectingId(null)} className="px-4 py-2 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer hover:border-ivory-dim transition-colors">Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </StaggerItem>
          )}
        </StaggerGroup>
      </div>
    </div>
  );
}
