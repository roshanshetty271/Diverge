import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "react-oidc-context";
import App from "@/App";
import { ToastProvider } from "@/components/Toast";
import { cognitoAuthConfig, isCognitoConfigured } from "@/utils/auth";
import "@/styles/theme.css";

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