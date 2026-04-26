# DIVERGE

A decision intelligence engine that spawns two AI versions of your future self and lets them debate.

You enter a fork in the road. Two agents wake up, one who stayed, one who jumped. They argue across five rounds: the money, the identity shift, the regret, the ripple effects. You watch. Then you decide.

Built for overthinkers, the anxious, and anyone who's ever been awake at 3am running scenarios.

Team Sic Mundus | AWS 10,000 AIdeas Competition | Daily Life Enhancement

## How It Works

1. Pick your fork. Career change, new city, startup, relationship, lifestyle shift, or write your own.
2. Add context. Finances, values, writing samples. All optional. The more you share, the sharper the debate.
3. Watch the debate. Two AI agents argue your decision across 5 structured rounds: opening statements, finances or emotions depending on the decision, identity, regret, and final arguments.
4. Read the verdict. A neutral judge summarizes where each path wins, surfaces your blind spots, and tells you the question you should actually be asking.

## What Makes It Different

**Token-by-token streaming.** Watch agents type their arguments in real time via SSE. Not blocks of text appearing at once — actual live thought generation.

**User interjection.** Between rounds, redirect the debate: "But what about the kids?" Both agents factor your input into their next argument.

**Adaptive rounds.** Financial decisions get salary and savings analysis. Relationship decisions get emotional cost and reward. The debate adapts to you.

**Voice matching.** Paste some texts or emails. The agents argue in your voice, not generic assistant speak.

**Monte Carlo grounding.** Financial simulations and probability models back up the arguments with real numbers.

**Animated fork visualization.** An SVG showing two diverging life paths with milestone nodes at Year 1, 3, 5, 10, and Deathbed. Click milestones to see snapshots.

**Sentiment analysis (scaffolded).** When Amazon Comprehend is available, emotional tone shifts per round are tracked for each path. On the current deployment this tab is hidden until Comprehend access is restored.

**Shareable links.** Share any debate as a read-only URL. Judges, friends, or your therapist can see the full debate.

**Voice input.** Speak your decision options via browser speech recognition.

**PDF export.** Download a branded dark-themed decision report with full transcript, verdict, and resources.

**Decision journal.** Every debate is logged. Record which path you chose. Reflect with satisfaction ratings over time.

## The Stack

Diverge was designed around a full AWS stack but currently runs in a leaner configuration while Bedrock model access, Comprehend, AgentCore Memory, and CloudFront are pending. All AWS integrations are scaffolded and will re-activate when account access is restored.

| Layer | Live today | Scaffolded / pending access |
|-------|------------|-----------------------------|
| Frontend | React 18, Vite, Tailwind CSS 4, Framer Motion, Recharts — hosted on Vercel | CloudFront + S3 origin-access wiring |
| Backend | FastAPI, Strands Agents SDK, Pydantic v2 — served via AWS Lambda + API Gateway | |
| AI models | OpenAI `gpt-4o-mini` (debate rounds, verdict, timeline) | Amazon Bedrock Nova Pro / Nova Lite |
| RAG | Pre-curated resource library | Bedrock Knowledge Bases (S3 data source) |
| Safety | Custom Python content guardrails + style validator with rewrite loop | Bedrock Guardrails (provider-side) |
| Analytics | Monte Carlo financial simulation (Python) | Amazon Comprehend sentiment |
| Voice | Browser `SpeechRecognition`, Web Speech TTS | Amazon Polly Neural + SSML |
| Email | Amazon SES (check-ins + results) | |
| Data | Amazon DynamoDB (debates, users, sessions, shared links, interjections, finalization progress) | |
| Auth | Amazon Cognito (OIDC, hosted UI) | |
| Memory | Per-session DynamoDB state with checkpointed resume | AgentCore Memory persistence |
| Observability | CloudWatch logs + alarms | AWS X-Ray tracing |

## Local Development

Prerequisites: Python 3.12+, Node.js 18+, an OpenAI API key (default provider). AWS credentials are required only if you are exercising SES, DynamoDB, Cognito, or Bedrock-backed paths.

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

App runs at `http://localhost:5173`. Backend at `http://localhost:8000`.
`npm run dev` is the local-first workflow: the browser stays on same-origin `/api`, and Vite proxies requests to the local FastAPI server.

For a rare live AWS smoke test after local validation:
```bash
cd frontend
npm run dev:aws
```

Deployed browsers should also stay same-origin. Vercel rewrites `/api/debate/start`, `/api/debate/session/*`, `/api/debate/stream*`, and `/api/debate/interject` to the long-running AWS Function URL, while the rest of `/api/*` goes to API Gateway. CloudFront should mirror that same path split once it is available.

## Sic Mundus Creatus Est.

Thus the world is created.
