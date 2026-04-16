import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import { useDivergeAuth } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import {
  loadImportedLocalDebateIds,
  loadLocalJournalEntries,
  markAutosaved,
  markImportedLocalDebates,
} from "../utils/debateStorage";
import { getJournal, reflectOnDebate, saveDebate } from "../utils/api";
import type { JournalEntry } from "../types";

interface ExtendedEntry extends JournalEntry {
  chosen_path?: string;
  satisfaction_rating?: number;
  reflection_note?: string;
  source: "cloud" | "local";
}

function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function buildSummary(item: Record<string, unknown>): string | undefined {
  const fromItem = item.summary;
  if (typeof fromItem === "string" && fromItem.trim()) {
    return fromItem.trim().slice(0, 120);
  }

  const verdict = item.verdict;
  if (typeof verdict === "string" && verdict.trim()) {
    return stripMarkdown(verdict).slice(0, 120);
  }

  return undefined;
}

function mergeEntries(localEntries: ExtendedEntry[], cloudEntries: ExtendedEntry[]): ExtendedEntry[] {
  const merged = new Map<string, ExtendedEntry>();

  for (const entry of localEntries) {
    merged.set(entry.id, entry);
  }
  for (const entry of cloudEntries) {
    merged.set(entry.id, entry);
  }

  return Array.from(merged.values()).sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
  );
}

function toLocalEntries(): ExtendedEntry[] {
  return loadLocalJournalEntries().map((item) => ({
    ...item,
    source: "local" as const,
  }));
}

function toCloudEntries(items: Record<string, unknown>[]): ExtendedEntry[] {
  return (items || []).map((item: Record<string, unknown>) => ({
    id: (item.debate_id as string) || String(Math.random()),
    pathA: (item.path_a as string) || "Option A",
    pathB: (item.path_b as string) || "Option B",
    summary: buildSummary(item),
    date: (item.created_at as string) || new Date().toISOString(),
    source: "cloud",
    data: item as unknown as JournalEntry["data"],
    input: (item.input as JournalEntry["input"]) || undefined,
    chosen_path: (item.chosen_path as string) || undefined,
    satisfaction_rating: (item.satisfaction_rating as number) || undefined,
    reflection_note: (item.reflection_note as string) || undefined,
  }));
}

export default function Journal() {
  const navigate = useNavigate();
  const { token, login, isAuthenticated, userId } = useDivergeAuth();
  const { toast } = useToast();
  const [localEntries, setLocalEntries] = useState<ExtendedEntry[]>([]);
  const [cloudEntries, setCloudEntries] = useState<ExtendedEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [importingLocal, setImportingLocal] = useState(false);
  const [reflectingId, setReflectingId] = useState<string | null>(null);
  const [reflectSatisfaction, setReflectSatisfaction] = useState(5);
  const [reflectNote, setReflectNote] = useState("");

  useEffect(() => {
    let cancelled = false;
    const nextLocalEntries = toLocalEntries();
    setLocalEntries(nextLocalEntries);

    if (!token) {
      setCloudEntries([]);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    getJournal(token)
      .then((result) => {
        if (cancelled) return;
        setCloudEntries(toCloudEntries(result.items || []));
      })
      .catch((err) => {
        if (!cancelled) {
          setCloudEntries([]);
          toast(
            "Failed to load cloud journal: " +
              (err instanceof Error ? err.message : "Unknown error"),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, toast]);

  const handleReflect = async (debateId: string) => {
    if (!token) return;
    try {
      await reflectOnDebate(debateId, reflectSatisfaction, reflectNote, token);
      setCloudEntries((prev) =>
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
      toast("Couldn't save reflection. Try again.");
    }
  };

  const handleImportLocalDebates = async () => {
    if (!token || !userId || importableEntries.length === 0 || importingLocal) return;

    setImportingLocal(true);
    const importedDebateIds: string[] = [];
    let failedCount = 0;

    for (const entry of importableEntries) {
      if (!entry.data || !entry.input) {
        failedCount += 1;
        continue;
      }

      try {
        await saveDebate({ debate_data: { ...entry.data, input: entry.input } }, token);
        importedDebateIds.push(entry.id);
        markAutosaved("cloud", entry.id);
      } catch {
        failedCount += 1;
      }
    }

    if (importedDebateIds.length > 0) {
      markImportedLocalDebates(userId, importedDebateIds);
    }

    try {
      const refreshed = await getJournal(token);
      setCloudEntries(toCloudEntries(refreshed.items || []));
    } catch {
      // The import already succeeded for some entries; keep the UI usable and let next refresh reconcile.
    } finally {
      setImportingLocal(false);
    }

    if (importedDebateIds.length > 0 && failedCount === 0) {
      toast(`Imported ${importedDebateIds.length} local debate${importedDebateIds.length === 1 ? "" : "s"} to your cloud journal.`, "success");
      return;
    }

    if (importedDebateIds.length > 0) {
      toast(
        `Imported ${importedDebateIds.length} local debate${importedDebateIds.length === 1 ? "" : "s"}. ${failedCount} still need${failedCount === 1 ? "s" : ""} a retry.`,
        "info",
      );
      return;
    }

    toast("Couldn't import your local debates right now. Try again.", "error");
  };

  const openJournalEntry = (entry: ExtendedEntry) => {
    if (!entry.data || !entry.input) {
      toast("This journal entry is missing its saved debate details.");
      return;
    }

    const route = entry.data?.verdict?.trim() ? "/verdict" : "/debate";
    navigate(route, {
      state: {
        debate: entry.data,
        input: entry.input,
        fromJournal: true,
      },
    });
  };

  const debates = mergeEntries(localEntries, cloudEntries);
  const cloudDebateIds = new Set(cloudEntries.map((entry) => entry.id));
  const importedDebateIds = new Set(userId ? loadImportedLocalDebateIds(userId) : []);
  const importableEntries =
    isAuthenticated && userId
      ? localEntries.filter(
          (entry) =>
            Boolean(entry.data && entry.input) &&
            !cloudDebateIds.has(entry.id) &&
            !importedDebateIds.has(entry.id),
        )
      : [];
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
      <div className="max-w-4xl mx-auto">
        <StaggerGroup>
          <StaggerItem>
            <h1 className="font-display text-2xl text-ivory" style={{ fontWeight: 400 }}>
              Decision Journal
            </h1>
            <p className="text-ivory-dim text-sm mt-1">Every choice shapes your world.</p>
          </StaggerItem>

          {!isAuthenticated && (
            <StaggerItem className="mt-6">
              <div className="rounded-lg border border-surface-light bg-surface px-4 py-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-ivory text-sm">Guest debates are saved on this device.</p>
                  <p className="text-ivory-faint text-xs mt-1">
                    Sign in if you want them synced to your cloud journal too.
                  </p>
                </div>
                <button
                  onClick={() => login()}
                  className="px-4 py-2 rounded-lg text-xs border border-path-risk text-path-risk cursor-pointer transition-colors duration-200 hover:bg-path-risk hover:text-void"
                >
                  Sign In to Sync
                </button>
              </div>
            </StaggerItem>
          )}

          {isAuthenticated && importableEntries.length > 0 && (
            <StaggerItem className="mt-6">
              <div className="rounded-xl border border-path-safe/30 bg-path-safe/5 px-5 py-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-path-safe text-[10px] font-mono uppercase tracking-[0.3em] mb-2">
                    Import from this device
                  </p>
                  <p className="text-ivory text-sm">
                    You have {importableEntries.length} local debate{importableEntries.length === 1 ? "" : "s"} saved on this device that are not in your cloud journal yet.
                  </p>
                  <p className="text-ivory-faint text-xs mt-1">
                    Import is one-time for this signed-in account. Your local copies stay here too.
                  </p>
                </div>
                <button
                  onClick={() => void handleImportLocalDebates()}
                  disabled={importingLocal}
                  className="px-4 py-2 rounded-lg text-xs border border-path-safe text-path-safe cursor-pointer transition-colors duration-200 hover:bg-path-safe hover:text-void disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {importingLocal ? "Importing..." : `Import ${importableEntries.length} debate${importableEntries.length === 1 ? "" : "s"}`}
                </button>
              </div>
            </StaggerItem>
          )}

          {isEmpty && (
            <StaggerItem className="mt-24 text-center">
              <p className="text-ivory-dim italic text-sm max-w-xs mx-auto leading-relaxed">
                &ldquo;The spinning wheel turns, round and round in a circle. Each fate tied to the next.&rdquo;
              </p>
              <p className="text-ivory-faint text-xs mt-6">Your first decision awaits.</p>
              <button
                onClick={() => navigate("/decide")}
                className="mt-6 px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-all duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]"
              >
                Make a decision &rarr;
              </button>
            </StaggerItem>
          )}

          {!isEmpty && (
            <StaggerItem className="mt-8">
              <div className="flex flex-col">
                {debates.map((d) => (
                  <div key={d.id} className="py-4 border-b border-surface-light">
                    <button
                      onClick={() => openJournalEntry(d)}
                      className="w-full text-left transition-colors duration-200 cursor-pointer group"
                    >
                      <div className="flex items-center gap-2">
                        <p className="text-ivory text-sm group-hover:text-path-risk transition-colors duration-200 truncate flex-1">
                          {d.pathA} vs. {d.pathB}
                        </p>
                        <span
                          className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                            d.source === "cloud"
                              ? "border-path-safe text-path-safe"
                              : "border-ivory-dim/40 text-ivory-dim"
                          }`}
                        >
                          {d.source === "cloud" ? "Cloud" : "This device"}
                        </span>
                        {d.chosen_path && (
                          <span
                            className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                              d.chosen_path === d.pathA
                                ? "border-path-safe text-path-safe"
                                : "border-path-risk text-path-risk"
                            }`}
                          >
                            Chose:{" "}
                            {d.chosen_path.length > 18
                              ? d.chosen_path.slice(0, 18) + "..."
                              : d.chosen_path}
                          </span>
                        )}
                      </div>
                      {d.summary && (
                        <p className="text-path-risk text-xs mt-1 truncate">
                          Verdict: {d.summary}
                          {d.summary.length >= 120 ? "..." : ""}
                        </p>
                      )}
                      <p className="text-ivory-faint/50 text-xs font-mono mt-1">
                        {new Date(d.date).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </p>
                    </button>

                    {d.satisfaction_rating && (
                      <div className="mt-2 ml-1 flex items-center gap-2 text-xs text-ivory-dim">
                        <span className="font-mono">
                          Satisfaction: {d.satisfaction_rating}/10
                        </span>
                        {d.reflection_note && (
                          <span className="italic truncate max-w-[200px]">
                            &ldquo;{d.reflection_note}&rdquo;
                          </span>
                        )}
                      </div>
                    )}

                    {d.source === "cloud" && d.chosen_path && !d.satisfaction_rating && (
                      <button
                        onClick={() => setReflectingId(d.id)}
                        className="mt-2 text-xs text-ivory-faint hover:text-ivory transition-colors cursor-pointer"
                      >
                        Reflect on this decision &rarr;
                      </button>
                    )}

                    {reflectingId === d.id && (
                      <div className="mt-3 bg-surface rounded-lg border border-surface-light p-4">
                        <p className="text-ivory text-sm mb-3">
                          How satisfied are you with this choice?
                        </p>
                        <div className="flex items-center gap-3 mb-3">
                          <input
                            type="range"
                            min={1}
                            max={10}
                            value={reflectSatisfaction}
                            onChange={(e) =>
                              setReflectSatisfaction(parseInt(e.target.value, 10))
                            }
                            className="flex-1 accent-path-risk"
                          />
                          <span className="text-ivory font-mono text-sm w-8 text-center">
                            {reflectSatisfaction}
                          </span>
                        </div>
                        <textarea
                          value={reflectNote}
                          onChange={(e) => setReflectNote(e.target.value.slice(0, 1000))}
                          placeholder="Any thoughts on how it went? (optional)"
                          rows={2}
                          className="w-full bg-void border border-surface-light rounded-lg p-3 text-ivory text-sm resize-none focus:border-ivory-dim focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                        />
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => handleReflect(d.id)}
                            className="px-4 py-2 rounded-lg text-sm bg-path-risk text-void font-medium cursor-pointer"
                          >
                            Save Reflection
                          </button>
                          <button
                            onClick={() => setReflectingId(null)}
                            className="px-4 py-2 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer hover:border-ivory-dim transition-colors"
                          >
                            Cancel
                          </button>
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
