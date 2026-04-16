/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE: string;
  readonly VITE_API_URL: string;
  readonly VITE_DEBATE_URL: string;
  readonly VITE_CHECKPOINTED_DEBATE: string;
  readonly VITE_COGNITO_REGION: string;
  readonly VITE_COGNITO_USER_POOL_ID: string;
  readonly VITE_COGNITO_CLIENT_ID: string;
  readonly VITE_COGNITO_DOMAIN: string;
  readonly VITE_REDIRECT_URI: string;
  readonly VITE_TURNSTILE_SITE_KEY: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
