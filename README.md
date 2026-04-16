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

**Sentiment analysis.** Amazon Comprehend tracks emotional tone shifts across rounds for each path.

**Shareable links.** Share any debate as a read-only URL. Judges, friends, or your therapist can see the full debate.

**Voice input.** Speak your decision options via browser speech recognition.

**PDF export.** Download a branded dark-themed decision report with full transcript, verdict, and resources.

**Decision journal.** Every debate is logged. Record which path you chose. Reflect with satisfaction ratings over time.

## The Stack (14 AWS Services)

| Layer | Tech |
|-------|------|
| Frontend | React 18, Vite, Tailwind CSS 4, Framer Motion, Recharts |
| Backend | FastAPI, Strands Agents SDK, Pydantic |
| AI Models | Amazon Bedrock (Nova Pro v1, Nova Lite v1) |
| RAG | Bedrock Knowledge Bases (S3 data source) |
| Safety | Bedrock Guardrails + custom regex defense-in-depth |
| Analytics | Amazon Comprehend (sentiment), Monte Carlo (financial) |
| Voice | Amazon Polly Neural (TTS with SSML), Browser SpeechRecognition |
| Email | Amazon SES (check-ins + results) |
| Data | Amazon DynamoDB (debates, users, shared links) |
| Auth | Amazon Cognito (OIDC, hosted UI) |
| Compute | AWS Lambda (2 functions), Amazon API Gateway |
| Hosting | Amazon S3 + CloudFront (OAC) |
| Observability | AWS X-Ray (distributed tracing), CloudWatch (alarms) |

## Local Development

Prerequisites: Python 3.12+, Node.js 18+, AWS credentials configured, Amazon Bedrock model access enabled.

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
