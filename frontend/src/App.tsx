import { lazy, Suspense } from "react";
import { Routes, Route, useLocation } from "react-router-dom";
import ErrorBoundary from "@/components/ErrorBoundary";
import RequireAuth from "@/components/RequireAuth";
import Navbar from "@/components/Navbar";
import SafetyFooter from "@/components/SafetyFooter";
import { isCognitoConfigured } from "@/utils/auth";

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

const HIDE_NAVBAR_PATHS = ["/loading", "/crisis"];

export default function App() {
  const location = useLocation();
  const showNavbar = !HIDE_NAVBAR_PATHS.includes(location.pathname);

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-void text-ivory font-body">
        {showNavbar && <Navbar />}
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
            <Route path="/journal" element={<RequireAuth fallbackMessage="Sign in to view your Decision Journal."><Journal /></RequireAuth>} />
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