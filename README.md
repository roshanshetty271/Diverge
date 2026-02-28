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

Adaptive rounds. Financial decisions get salary and savings analysis. Relationship decisions get emotional cost and reward. The debate adapts to you.

Voice matching. Paste some texts or emails. The agents argue in your voice, not generic assistant speak.

Monte Carlo grounding. Financial simulations and probability models back up the arguments with real numbers.

Decision journal. Every debate is logged. Over time, you calibrate your intuition.

## The Stack

| Layer | Tech |
|-------|------|
| Frontend | React, Vite, Tailwind CSS, Framer Motion |
| Backend | FastAPI, Strands Agents SDK, Pydantic |
| AI | Amazon Bedrock (Nova Pro / Nova Lite) |
| Data | Amazon DynamoDB |
| Auth | Amazon Cognito |
| Infra | AWS Lambda, API Gateway, S3, CloudFront |

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

## Sic Mundus Creatus Est.

Thus the world is created.
