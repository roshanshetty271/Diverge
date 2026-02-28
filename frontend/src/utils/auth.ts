const COGNITO_REGION = import.meta.env.VITE_COGNITO_REGION || "us-east-1";
const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID || "";
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || "";
const COGNITO_DOMAIN = import.meta.env.VITE_COGNITO_DOMAIN || "";
const REDIRECT_URI = import.meta.env.VITE_REDIRECT_URI || window.location.origin;

export const cognitoAuthConfig = {
  authority: `https://cognito-idp.${COGNITO_REGION}.amazonaws.com/${USER_POOL_ID}`,
  client_id: CLIENT_ID,
  redirect_uri: REDIRECT_URI,
  response_type: "code",
  scope: "email openid profile",
  automaticSilentRenew: false,
  revokeTokenTypes: ["refresh_token"],
  onSigninCallback: (): void => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

export function cognitoLogout(): void {
  const logoutUri = encodeURIComponent(REDIRECT_URI);
  window.location.href = `${COGNITO_DOMAIN}/logout?client_id=${CLIENT_ID}&logout_uri=${logoutUri}`;
}

export function isCognitoConfigured(): boolean {
  return Boolean(USER_POOL_ID && CLIENT_ID);
}
