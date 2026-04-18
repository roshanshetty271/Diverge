import { lazy, Suspense, useEffect, useRef } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import ErrorBoundary from "@/components/ErrorBoundary";
import Navbar from "@/components/Navbar";
import SafetyFooter from "@/components/SafetyFooter";
import { useToast } from "@/components/Toast";
import { useDivergeAuth } from "@/hooks/useAuth";
import { getJournal } from "@/utils/api";
import { isCognitoConfigured } from "@/utils/auth";
import { loadImportedLocalDebateIds, loadLocalJournalEntries } from "@/utils/debateStorage";

// Lazy-loaded pages — each becomes a separate chunk (Vite best practice)
// Only Landing loads eagerly since it's always the first page
import Landing from "@/pages/Landing";
const Templates = lazy(() => import("@/pages/Templates"));
const Intake = lazy(() => import("@/pages/Intake"));
const Loading = lazy(() => import("@/pages/Loading"));
const Debate = lazy(() => import("@/pages/Debate"));
const Verdict = lazy(() => import("@/pages/Verdict"));
const Journal = lazy(() => import("@/pages/Journal"));
const SharedDebate = lazy(() => import("@/pages/SharedDebate"));
const ErrorPage = lazy(() => import("@/pages/ErrorPage"));
const CrisisResources = lazy(() => import("@/components/CrisisResources"));

// Minimal fallback that matches the void theme (not a white flash)
function PageFallback() {
  return (
    <div className="min-h-screen bg-void flex items-center justify-center">
      <p className="text-ivory-faint text-sm font-mono animate-pulse">Loading...</p>
    </div>
  );
}

const HIDE_NAVBAR_PATHS = ["/crisis"];

function JournalImportNotifier() {
  const { isAuthenticated, token, userId } = useDivergeAuth();
  const { toast } = useToast();
  const previousSignedIn = useRef(false);
  const notifiedUsers = useRef<Set<string>>(new Set());

  useEffect(() => {
    const signedIn = Boolean(isAuthenticated && token && userId);
    const justSignedIn = signedIn && !previousSignedIn.current;
    previousSignedIn.current = signedIn;

    if (!justSignedIn || !token || !userId || notifiedUsers.current.has(userId)) {
      return;
    }

    const importedIds = new Set(loadImportedLocalDebateIds(userId));
    const localCandidates = loadLocalJournalEntries().filter(
      (entry) => entry.data && entry.input && !importedIds.has(entry.id),
    );

    if (localCandidates.length === 0) {
      return;
    }

    let cancelled = false;

    getJournal(token)
      .then((result) => {
        if (cancelled) return;

        const cloudIds = new Set(
          (result.items || [])
            .map((item) => item.debate_id)
            .filter((debateId): debateId is string => typeof debateId === "string" && debateId.length > 0),
        );

        const importableCount = localCandidates.filter((entry) => !cloudIds.has(entry.id)).length;
        if (importableCount > 0) {
          toast("You have local debates on this device. Open Journal to import them.", "info");
          notifiedUsers.current.add(userId);
        }
      })
      .catch(() => {
        // Keep the Journal experience resilient; import prompt still exists in the page itself.
      });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, token, toast, userId]);

  return null;
}

export default function App() {
  const location = useLocation();
  const showNavbar = !HIDE_NAVBAR_PATHS.includes(location.pathname);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [location.pathname]);

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-void text-ivory font-body">
        {showNavbar && <Navbar />}
        <JournalImportNotifier />
        {!isCognitoConfigured() && import.meta.env.DEV && (
          <div className="bg-surface border-b border-surface-light px-4 py-2 text-center">
            <p className="text-ivory-faint text-xs font-mono">
              Auth disabled — set VITE_COGNITO_* env vars to enable sign-in
            </p>
          </div>
        )}
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/decide" element={<Templates />} />
            <Route path="/intake" element={<Intake />} />
            <Route path="/loading" element={<Loading />} />
            <Route path="/debate" element={<Debate />} />
            <Route path="/verdict" element={<Verdict />} />
            <Route path="/journal" element={<Journal />} />
            <Route path="/d/:shareId" element={<SharedDebate />} />
            <Route path="/crisis" element={<CrisisResources />} />
            <Route path="*" element={<ErrorPage />} />
          </Routes>
        </Suspense>
        {location.pathname !== "/" && <SafetyFooter />}
      </div>
    </ErrorBoundary>
  );
}
