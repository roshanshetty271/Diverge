import { useAuth as useOidcAuth } from "react-oidc-context";
import { isCognitoConfigured, cognitoLogout } from "../utils/auth";
import { useToast } from "../components/Toast";
import type { DivAuthState } from "../types";

const NOOP_AUTH: Omit<DivAuthState, "login"> = {
  isAuthenticated: false,
  isLoading: false,
  user: null,
  error: null,
  token: null,
  userId: null,
  email: null,
  logout: () => {},
};

export function useDivergeAuth(): DivAuthState {
  const { toast } = useToast();

  if (!isCognitoConfigured()) {
    return {
      ...NOOP_AUTH,
      login: () => toast("Sign-in requires Cognito configuration. Set VITE_COGNITO_* env vars.", "info"),
    };
  }

  const auth = useOidcAuth();

  return {
    isAuthenticated: auth.isAuthenticated,
    isLoading: auth.isLoading,
    user: auth.user,
    error: auth.error || null,
    token: auth.user?.access_token || null,
    userId: auth.user?.profile?.sub || null,
    email: (auth.user?.profile?.email as string) || null,
    login: () => auth.signinRedirect(),
    logout: async () => {
      await auth.removeUser();
      cognitoLogout();
    },
  };
}
