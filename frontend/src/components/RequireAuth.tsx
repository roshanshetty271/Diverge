import { useDivergeAuth } from "../hooks/useAuth";
import { StaggerGroup, StaggerItem } from "./Stagger";

interface Props {
  children: React.ReactNode;
  fallbackMessage?: string;
}

export default function RequireAuth({ children, fallbackMessage = "Sign in to access this page." }: Props) {
  const { isAuthenticated, isLoading, login } = useDivergeAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-void flex items-center justify-center">
        <p className="text-ivory-faint text-sm font-mono animate-pulse">Checking authentication...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-void flex items-center justify-center px-6">
        <StaggerGroup className="text-center">
          <StaggerItem>
            <p className="text-ivory-dim text-sm">{fallbackMessage}</p>
          </StaggerItem>
          <StaggerItem>
            <button
              onClick={() => login()}
              className="mt-6 px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-all duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]"
            >
              Sign in
            </button>
          </StaggerItem>
        </StaggerGroup>
      </div>
    );
  }

  return <>{children}</>;
}
