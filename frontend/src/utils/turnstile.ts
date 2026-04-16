const TURNSTILE_SCRIPT_ID = "diverge-turnstile-script";
const TURNSTILE_SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || "";

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        options: {
          sitekey: string;
          size: "invisible";
          action?: string;
          callback: (token: string) => void;
          "error-callback": () => void;
          "expired-callback": () => void;
        },
      ) => string;
      execute: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
  }
}

type TurnstileApi = NonNullable<Window["turnstile"]>;

let turnstileLoader: Promise<TurnstileApi> | undefined;

export function isTurnstileConfigured(): boolean {
  return Boolean(TURNSTILE_SITE_KEY);
}

function loadTurnstileScript(): Promise<TurnstileApi> {
  if (window.turnstile) {
    return Promise.resolve(window.turnstile);
  }

  if (turnstileLoader) {
    return turnstileLoader;
  }

  const loader: Promise<TurnstileApi> = new Promise<TurnstileApi>((resolve, reject) => {
    const existing = document.getElementById(TURNSTILE_SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => {
        if (window.turnstile) {
          resolve(window.turnstile);
          return;
        }
        reject(new Error("Human verification failed to load."));
      }, { once: true });
      existing.addEventListener("error", () => reject(new Error("Human verification failed to load.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = TURNSTILE_SCRIPT_ID;
    script.src = TURNSTILE_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => {
      if (window.turnstile) {
        resolve(window.turnstile);
        return;
      }
      reject(new Error("Human verification failed to load."));
    };
    script.onerror = () => reject(new Error("Human verification failed to load."));
    document.head.appendChild(script);
  }).catch((error) => {
    turnstileLoader = undefined;
    throw error;
  });

  turnstileLoader = loader;
  return turnstileLoader;
}

export async function getTurnstileToken(action: string = "debate_start"): Promise<string | null> {
  if (!isTurnstileConfigured()) {
    return null;
  }

  const turnstile = await loadTurnstileScript();

  return new Promise((resolve, reject) => {
    const container = document.createElement("div");
    container.setAttribute("aria-hidden", "true");
    container.style.position = "fixed";
    container.style.inset = "0";
    container.style.pointerEvents = "none";
    container.style.opacity = "0";
    document.body.appendChild(container);

    let widgetId = "";
    let settled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const cleanup = () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      if (widgetId) {
        try {
          turnstile.remove(widgetId);
        } catch {
          // no-op
        }
      }
      container.remove();
    };

    const settle = (fn: () => void) => {
      if (settled) return;
      settled = true;
      cleanup();
      fn();
    };

    widgetId = turnstile.render(container, {
      sitekey: TURNSTILE_SITE_KEY,
      size: "invisible",
      action,
      callback: (token) => settle(() => resolve(token)),
      "error-callback": () =>
        settle(() => reject(new Error("Please verify you're human and try again."))),
      "expired-callback": () =>
        settle(() => reject(new Error("Human verification expired. Please try again."))),
    });

    timeoutId = setTimeout(() => {
      settle(() => reject(new Error("Human verification timed out. Please try again.")));
    }, 15000);

    turnstile.execute(widgetId);
  });
}
