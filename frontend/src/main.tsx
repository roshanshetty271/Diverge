import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "react-oidc-context";
import App from "@/App";
import { ToastProvider } from "@/components/Toast";
import { cognitoAuthConfig, isCognitoConfigured } from "@/utils/auth";
import "@/styles/theme.css";

// When Vercel points the production alias at a new deployment, an older open tab
// can still ask for code-split chunks from the previous build. Vite emits this
// event so the app can recover instead of crashing on route change.
window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  window.location.reload();
});

const root = ReactDOM.createRoot(document.getElementById("root")!);

const app = (
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>
);

root.render(
  isCognitoConfigured() ? <AuthProvider {...cognitoAuthConfig}>{app}</AuthProvider> : app
);
