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

**Streamed rounds.** Each round is sent to the browser as server-sent events and revealed with a typewriter effect. A round's text is generated and checked by the content guardrails first, then sent in chunks.

**User interjection.** The debate pauses after each round. Add context before continuing ("But what about the kids?") and both future selves factor it into the next round.

**Adaptive rounds.** Financial decisions get salary and savings analysis. Relationship decisions get emotional cost and reward. The debate adapts to you.

**Voice matching.** Paste some texts or emails. The agents argue in your voice, not generic assistant speak.

**Monte Carlo grounding.** When you give financial details, a Monte Carlo runway simulation runs before the debate and its numbers are added to the debate prompts.

**Fork timeline.** The verdict page shows two diverging life paths with milestones at Year 1, 3, 5, 10 and Final Words. Click a milestone to read that snapshot.

**Sentiment analysis.** Amazon Comprehend scores the emotional tone of each path's argument every round, shown in the Sentiment chart.

**Shareable links.** Share any debate as a read-only URL with the rounds and the verdict. Your finances, writing samples, name and age are not included.

**Voice input.** Speak your decision options via browser speech recognition.

**PDF export.** Download a branded dark-themed decision report with full transcript, verdict, and resources.

**Decision journal.** Finished debates are saved to your journal (in your account when signed in, otherwise in the browser). Record which path you chose and reflect with satisfaction ratings over time.

## The Stack

Diverge runs on Amazon Bedrock with Comprehend sentiment enabled. A few AWS integrations are scaffolded in the code but switched off in the current deployment, listed in the right-hand column.

| Layer | Live today | Scaffolded / pending access |
|-------|------------|-----------------------------|
| Frontend | React 18, Vite, Tailwind CSS 4, Framer Motion, Recharts — hosted on Vercel | CloudFront + S3 origin-access wiring |
| Backend | FastAPI, Strands Agents SDK, Pydantic v2 — served via AWS Lambda + API Gateway | |
| AI models | Amazon Bedrock: Nova Pro (debate rounds, verdict, timeline), Nova Lite (round metrics) | OpenAI `gpt-4o-mini` via `DIVERGE_MODEL_PROVIDER=openai` (used for local development) |
| RAG | Pre-curated resource library | Bedrock Knowledge Bases (off: no knowledge base configured) |
| Safety | Custom Python content guardrails + style validator with rewrite loop | Bedrock Guardrails (provider-side) |
| Analytics | Monte Carlo financial simulation (Python), Amazon Comprehend sentiment | |
| Voice | Browser `SpeechRecognition`, Web Speech TTS | Amazon Polly Neural + SSML |
| Email | Amazon SES (check-ins + results) | |
| Data | Amazon DynamoDB (debates, users, sessions, shared links, interjections, finalization progress) | |
| Auth | Amazon Cognito (OIDC, hosted UI) | |
| Memory | Per-session DynamoDB state with checkpointed resume | AgentCore Memory persistence |
| Observability | CloudWatch logs + alarms, AWS X-Ray tracing | |

## Local Development

Prerequisites: Python 3.12+, Node.js 18+, and an OpenAI API key (the local default provider; production uses Bedrock). AWS credentials are required only if you are exercising SES, DynamoDB, Cognito, or Bedrock-backed paths.

Backend:
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
echo "DIVERGE_OPENAI_API_KEY=sk-..." > .env   # settings are read from DIVERGE_* variables
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

## Tests

```bash
pip install -r backend/requirements.txt pytest pytest-asyncio
python -m pytest backend/tests
cd frontend && npm ci && npm run build
```

CI (`.github/workflows/ci.yml`) runs the same backend tests and frontend build on every push to `main` and on pull requests. The tests use fakes and stubs only; they need no AWS access or API keys.

## Sic Mundus Creatus Est.

Thus the world is created.
