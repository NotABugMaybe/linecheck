# LineCheck

LineCheck is a configurable industrial visual inspection workflow platform. A profile binds one product and variant, defect taxonomy and acceptance rules, capture setup, thresholds, dataset version, and model version. A profile must be validated for its own factory and imaging conditions. This repository does not establish factory performance, safety, or regulatory compliance.

## Current implementation

- React + TypeScript responsive operations UI; FastAPI v1 JSON API; SQLAlchemy persistence (SQLite local, PostgreSQL in Compose); local image storage.
- Tenant-scoped organizations, initial admin registration, JWT sessions, role checks, profile drafts and config versioning, cloning, approval/suspension gates, image upload validation and SHA-256 deduplication, labels and split annotations, insufficiency/leakage training gates, inspection/review queue, append-only correction events, CSV export, health/readiness, request IDs.
- Unsafe and unapproved inference resolves to `needs_review` or `unknown`; this build intentionally ships no fabricated model metrics and no real training/inference worker. Training requests are gated but return a clear worker-not-installed message. No PLC/MES/camera connection is enabled.

## Architecture and flow

The browser uses the versioned `/api/v1` API. Auth establishes an organization-scoped JWT; every data lookup includes the token's organization. Images are format decoded and dimension limited before being named by content digest under `<storage>/<org>/<profile>/`. Labels and dataset splits attach to image records. A training request checks minimum labeled data in train/validation/test and verifies digest disjointness before recording a draft model request. Inference is advisory and explicitly unknown until an approved profile has a real runtime. Review corrections retain the original decision and create an audit event.

Modules: `backend/app/security.py` authentication and role checks; `models.py` relational entities; `main.py` organization-scoped API, ingestion, workflows, audit and reports; `frontend/src` operations interface. OpenAPI is served at `/api/v1/openapi.json` and Swagger UI at `/api/v1/docs`.

## Local development

Requirements: Python 3.12+, Node 22+, npm. From repository root:

```sh
cp .env.example .env
# Replace SECRET_KEY with output of: python -c 'import secrets; print(secrets.token_urlsafe(48))'
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
npm install
```

Start API and UI in separate terminals:

```sh
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
npm run dev
```

Open http://localhost:5173. Create the first local organization and admin account in the sign-in screen (password minimum 12 characters). Registration is available only with `DEVELOPMENT_MODE=true`; disable it in deployment. Local storage defaults under `backend/data/images`; local SQLite defaults to `backend/linecheck.db`.

Compose deployment-oriented setup:

```sh
cp .env.example .env
# Set strong SECRET_KEY and POSTGRES_PASSWORD; set DEVELOPMENT_MODE=false
# For controlled user provisioning, create users through an audited admin workflow before disabling signup.
docker compose up --build
```

UI: http://localhost:8080. API health/readiness: `/health`, `/ready`. Compose uses PostgreSQL and persistent image/database volumes; configure secrets through the environment, never commit `.env`.

## Roles and workflow

Roles are `org_admin`, `quality_manager`, `engineer`, `operator`, and `read_only_auditor`. Admin and quality manager can approve/suspend profiles and review audit events; engineers can configure profiles and request training; operators can label and review; auditors can read audit history. Provisioning of additional production accounts should be performed through a reviewed, audited identity workflow before deployment.

1. Create a site via `POST /api/v1/sites`; model the line/station metadata in your factory integration layer.
2. Create a profile via `POST /api/v1/profiles` with product, variant, defects, capture setup, thresholds. Configuration changes bump the version and mark approved work as needing validation.
3. Upload images using multipart `POST /api/v1/profiles/{id}/images`; annotate labels and split via `PATCH /api/v1/images/{id}/label`. Keep identical parts/production lots together when splitting; digest checks alone cannot detect near duplicates or correlated captures.
4. Request `POST /api/v1/profiles/{id}/train`. It requires 10 training labels and at least one validation and test label. It records no fake metrics. A production implementation must install a reproducible per-profile trainer/evaluator and record its artifact and measured metrics.
5. Approve only a validated candidate with `POST /api/v1/profiles/{id}/approve`; approvals are role-gated. The present build intentionally has no candidate-producing evaluator.
6. Station inspection uses `POST /api/v1/profiles/{id}/inspect`; until a validated runtime exists the response is unknown/needs-review. Review using `PATCH /api/v1/reviews/{id}`. Export with `GET /api/v1/reports/inspections.csv`.
7. Suspend when conditions change; collect data, retrain, evaluate, approve, then roll forward only after human review. Model rollback needs registry/runtime integration.

Example authenticated API calls (replace token and profile ID):

```sh
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/profiles
curl -H "Authorization: Bearer $TOKEN" -F file=@part.png http://localhost:8000/api/v1/profiles/1/images
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/reports/inspections.csv
```

## Security, privacy, retention, operations

Customer images remain local by default; no external AI service receives them. Upload size is limited, type is allowlisted, Pillow decode and pixel ceiling guard malformed/oversized images, and names are generated from the digest. Tenant ownership scopes API reads and writes. Passwords are bcrypt-hashed and bearer JWTs expire. Use TLS termination, strong secret rotation, rate limiting, CSRF protection if switching to cookies, backup encryption, and a managed identity flow before production. Rate limiting and cookie/CSRF support are not implemented in this local release. Audit rows are append-only by application convention, not cryptographically tamper-proof; harden DB privileges and export to immutable audit storage for deployment. There is no image delete/retention API yet; define retention, legal hold, erasure, and backup expiry before onboarding customer data.

Back up PostgreSQL with `pg_dump` and the image volume with a consistent object/filesystem snapshot; restore DB and image objects together, then validate counts and checksums. Configure S3-compatible storage by implementing the storage interface before using remote object storage. Current disk storage and single API process are not designed for high-volume line rates. Use external workers/queue, object storage, PostgreSQL, observability, and load testing for scale.

Threat assumptions include hostile uploads, cross-tenant IDs, compromised credentials, accidental profile drift, dataset leakage, and inference failures. Machine safety, target-market regulation, privacy obligations, and acceptable false-negative risk require qualified review for each intended use and market. No certification is claimed.

## Tests and CI

```sh
PYTHONPATH=backend SECRET_KEY=test-only-key-12345678901234567890 pytest -q backend/tests
npm run lint
npm run build
```

CI runs backend pytest and frontend type/build checks. The test suite covers registration/auth, tenant scoping, profile lifecycle gates, insufficient dataset handling, malicious image payload rejection, safe advisory inference, and immutable original decisions after correction. Full production-grade performance evaluation, stress testing, dependency scanning, and hardware integration remain to be added.

## Limitations before factory deployment

No trained model or performance claim is included. Training jobs do not run asynchronously yet; no validated inference runtime, calibrated score, localization output, batch queue, candidate evaluation metrics, rollback executor, image deletion workflow, line/station database model, camera adapter, MES/PLC integration, rate limiter, CSRF implementation, Alembic migration history, PDF reporting, monitoring/drift analytics, backup automation, or full operator UI workflows are present. Integration interfaces must remain simulated/disabled; this project never sends control signals. Obtain factory-specific data, camera/light hardware, representative evaluation, security review, operational validation, and regulatory/safety advice before use.
