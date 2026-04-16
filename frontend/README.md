# Diverge — Frontend

**Team Sic Mundus | AWS 10,000 AIdeas Competition**

A decision intelligence engine that spawns two AI versions of your future self
and lets them debate your biggest decision.

## Quick Start

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.example .env

# Start the local-first dev server
npm run dev
```

Open http://localhost:5173

`npm run dev` keeps the browser on same-origin `/api` and lets Vite proxy requests to a local backend on `http://localhost:8000`.

Start the backend in another terminal:

```bash
cd ../backend
uvicorn app.main:app --reload --port 8000
```

If you want an explicit live AWS smoke test after local validation, run:

```bash
npm run dev:aws
```

## Tech Stack

- **React 18** + **Vite** — fast build, static SPA output
- **Tailwind CSS v4** — utility-first styling
- **Framer Motion** — page transitions, typewriter effect, stagger animations
- **Recharts** — radar chart, timeline projections, regret accumulation
- **React Router v7** — client-side routing
- **Lucide React** — minimal icons

## Design System

Aesthetic: "Triquetra Notebook meets Bloomberg Terminal" — inspired by Netflix's Dark.

| Token | Value | Usage |
|-------|-------|-------|
| `void` | `#0a0a0a` | Page backgrounds |
| `surface` | `#141414` | Cards, containers |
| `surface-light` | `#1e1e1e` | Borders, dividers |
| `path-safe` | `#4a6fa5` | Safe/staying path (blue) |
| `path-risk` | `#d4a843` | Bold/risk path (amber) |
| `ivory` | `#f0ece2` | Primary text |
| `ivory-dim` | `#a09a8e` | Secondary text |

**Fonts:** Cinzel (display), DM Sans (body), JetBrains Mono (data)

## Pages

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Landing | Cinematic title screen |
| `/decide` | Templates | Pick a decision template |
| `/intake` | Intake | 3-step context form (all optional) |
| `/loading` | Loading | Waiting screen with Dark quotes |
| `/debate` | Debate | Split-screen debate with charts |
| `/verdict` | Verdict | Synthesis + hidden insight |
| `/journal` | Journal | Past debates (requires auth) |

## Build for Production

```bash
npm run build
```

Output goes to `dist/` — upload to S3 + CloudFront.

## Sic Mundus Creatus Est.
