import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const LOCAL_BACKEND_TARGET = "http://localhost:8000";

export default defineConfig({
  plugins: [
    react(),             // React Fast Refresh + JSX transform
    tailwindcss(),       // Tailwind v4
  ],
  resolve: {
    alias: { "@": "/src" }, // Import as @/components/X instead of ../../../components/X
  },
  server: {
    port: 5173,
    strictPort: true,
    // Dev proxy: /api calls go to FastAPI backend — avoids CORS in development
    proxy: {
      "/api": {
        target: LOCAL_BACKEND_TARGET,
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        // Split heavy libs into separate chunks for better caching
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-charts": ["recharts"],
          "vendor-motion": ["framer-motion"],
        },
      },
    },
  },
});
