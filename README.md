# ReconAudit — AI Finance Controller

ReconAudit closes a 60-order synthetic finance reconciliation batch: JSON orders, CSV settlements, and XML bank records are normalized; a deterministic rule engine matches them; a bounded evidence-only resolver investigates exceptions; every decision enters a SHA-256 hash chain; and the hidden answer key powers automatic evaluation.

## Client upload workflow

After starting the API, open `http://localhost:8000/` in your browser. Do not open `frontend/index.html` directly from File Explorer: browsers treat `file:` pages as isolated origins, which can prevent the client from reaching the API. Create one review workspace and upload:

- **Orders (JSON):** `id`, `reference`, `amount`, `currency`, `created_at`, `merchant`
- **Settlements (CSV):** `id`, `reference`, `amount`, `currency`, `settled_at`, `merchant`
- **Bank credits (XML):** `id`, `reference`, `amount`, `currency`, `credited_at`, `counterparty`

The app validates and retains malformed-row messages, permits replacement uploads,
then processes only the uploaded data. The dashboard exposes the normalized data,
matching rule/evidence, exceptions, tool trace, and ledger verification. Client
uploads intentionally do not display fabricated accuracy scores: accuracy requires
an independently verified answer key.

## Run locally

Copy [`.env.example`](.env.example) to `.env` and configure it locally. Fill in
`GEMINI_API_KEY` to enable Gemini 3.6 Flash function calling; SQLite is the default and
does not require database credentials. Use `.env.example` as the safe template.

Never commit `.env`, API keys, database credentials, private certificates, or service-account files.
The repository ignores these files by default. For deployment, store secrets in the deployment
platform's secret manager and provide only non-sensitive configuration through environment variables.

For the Buildathon demo, configure a real Gemini API key and use **Run synthetic
demo** in the dashboard. This executes the reproducible 60-record batch and
reports match rate, resolution accuracy, and honesty score.

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000/` in a browser. The API defaults to `http://localhost:8000`; edit `frontend/js/config.js` after deployment. API docs are at `http://localhost:8000/docs`.

Reconciliations run in the background so the page remains responsive while Gemini investigates exceptions. Keep the page open until the result screen appears; if Gemini is rate-limited, its required retry can take up to a minute.

## Test

```powershell
cd backend
py -m pytest
```

## Architecture

- Synthetic generator with fixed seed and separately stored ground truth
- JSON/CSV/XML parsers into a Pydantic canonical schema
- Explainable deterministic exact/window/typed-exception engine
- Four-tool, step-bounded, grounding-validated exception resolver
- SHA-256 tamper-evident audit chain
- Evaluation of throughput, accuracy, honesty, and false resolutions
- FastAPI APIs, Tailwind/vanilla-JS dashboard, Docker and SAM deployment scaffold

For deployment, configure managed Postgres through `DATABASE_URL`, supply `GEMINI_API_KEY` for a Gemini provider implementation, then deploy the Lambda image with SAM. The current local implementation deliberately works without external keys so judges can reproduce the pipeline.
