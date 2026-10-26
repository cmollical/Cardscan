# TallyBinder

Mobile Pokémon card intake, exact-condition market references, and personal inventory.
The repository remains `cmollical/Cardscan`; internal Python imports remain `cardscan`.

Capture front and back photos, manually select an exact catalog printing (or request
optional AI suggestions), confirm condition, retrieve a local SKU market reference,
and approve a listing. Review cards in a durable intake queue while capturing more.
The app never turns generic ungraded prices into condition-specific prices.
Market values exclude shipping and tax; your chosen selling price is separate.

**Personal research MVP.** Provider commercial licensing remains unresolved. AI
photo interpretation requires human review and does not constitute professional grading.
No paid AI calls are needed for the complete manual workflow.

## Start locally

Python 3.12+ and Node.js 22+ recommended. From the repository root:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-local.txt -r requirements-ai.txt -r requirements-history.txt
python -m cardscan.local_pricing.cli --db local-evidence/tallybinder.sqlite init
python -m cardscan.local_pricing.cli --db local-evidence/tallybinder.sqlite seed
export TALLYBINDER_DB="$PWD/local-evidence/tallybinder.sqlite"
export TALLYBINDER_AI_ENABLED=false
uvicorn cardscan.local_pricing.api:app --host 127.0.0.1 --port 8000 --workers 1
```

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. The seed command imports **dated October 26, 2026
source excerpts**, not live prices or a complete catalog. To use an existing database,
back it up, run `init` against its path to apply non-destructive migrations, and point
`TALLYBINDER_DB` at that path. No provider requests run during normal app use.

See **[mobile setup and operating guide](docs/tallybinder-mobile.md)** for iPhone
HTTPS testing, installation, configuration, API routes, security, tests and deployment
options. Backend API docs: http://127.0.0.1:8000/docs.

## Preserved pricing work

- [Local pricing database and controlled synchronization](docs/local-pricing-backend.md)
- [Backend readiness and 15-set expansion](docs/backend-readiness-2026-10-26.md)
- [Source verification](docs/reference-verification.md)
- [Historical research README](research/historical/cardscan-readme-before-tallybinder.md)

Existing deterministic valuation, AI research experiments, source evidence, and
append-only price histories are preserved. Historical archive backfill is not part
of this milestone. No repository rename, production deployment, Square integration,
full-catalog import, paid AI execution or hosted scheduler is performed.
