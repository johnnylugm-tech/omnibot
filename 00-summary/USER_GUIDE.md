# OmniBot — User Guide (How to Get Started)

> OmniBot is an enterprise-grade multi-platform customer service chatbot.
> One bot instance serves Telegram / LINE / Messenger / WhatsApp / Web / A2A agents
> with unified dialogue state, a 4-tier hybrid knowledge layer, and a
> 5-layer prompt-injection defence (PALADIN).
>
> **Status**: All phases P1–P8 complete (Gate 4 PASS, 100 FRs registered).
> This guide covers developer onboarding. End-user / admin docs live in
> `03-development/` after the admin WebUI is deployed.

---

## 1. Prerequisites

| Requirement | Version | Why |
|-------------|---------|-----|
| Python | **≥ 3.11** | `requires-python` in `pyproject.toml`; harness_cli rejects system Python 3.9 |
| Docker Engine + Compose plugin | ≥ 24 | Run the 7-container dev infra (postgres×2, redis, clamav, otel, prometheus, grafana) |
| Git | ≥ 2.30 | Submodule support (harness is a git submodule) |
| `uv` (recommended) **or** `pip` + venv | latest | Dependency manager |
| `openssl` | any | For ad-hoc TLS cert generation (Redis TLS, JWT) |
| ~6 GB free disk | — | Pulled images, build artifacts, mutation test caches |

**macOS note**: `pyproject.toml` dev extras reference a non-PyPI `gitleaks` binary.
`uv sync --extra dev` will fail on `gitleaks>=8.18` resolution. Install gitleaks
separately via Homebrew (`brew install gitleaks`) and use plain `uv sync`
(without `--extra dev`) for app deps. See `omnibot-env-check-gitleaks` memory.

---

## 2. Clone the Repository

```bash
# --recurse-submodules is REQUIRED: harness/ is a git submodule
git clone --recurse-submodules https://github.com/johnnylugm-tech/omnibot.git
cd omnibot

# Verify submodule populated
ls harness/harness_cli.py      # must exist
cat .gitmodules                # should reference [submodule "harness"]
```

If you forgot `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

---

## 3. Install Python Dependencies

```bash
# Option A: uv (fast, recommended)
uv sync                          # app deps only
uv sync --extra dev               # INCLUDES gitleaks pin (may fail on some hosts)

# Option B: pip + venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -e ".[dev]"          # see gitleaks note above
```

The project uses `03-development/src` as source root (see `setup.cfg` `pythonpath`).
`pip install -e .` registers the `app` package and the `omnibot` console script
(`uvicorn:run`).

Verify the install:

```bash
.venv/bin/python -c "import app; print(app.__file__)"
# Expected: .../03-development/src/app/__init__.py
```

---

## 4. Bring Up Dev Infrastructure

The dev stack has **7 containers** wired in `docker-compose.yml` (mirrors SAD §2.5
and the env-check result in `.sessi-work/env_check_result.json`).

```bash
# Generate dev TLS certs for Redis (one-time, only if using TLS)
mkdir -p deployment/redis/tls
openssl req -x509 -newkey rsa:2048 -days 365 -nodes \
  -keyout deployment/redis/tls/redis.key \
  -out    deployment/redis/tls/redis.crt \
  -subj "/CN=localhost"
cp deployment/redis/tls/redis.crt deployment/redis/tls/ca.crt

# Start everything
docker compose up -d
docker compose ps                  # all 7 should be 'healthy' within ~30s
```

Service → host port map:

| Service      | Image                              | Host port | Notes |
|--------------|------------------------------------|-----------|-------|
| pg-super     | pgvector/pgvector:pg16             | 5433      | Primary dev DB (pgvector extension enabled) |
| db           | postgres:16-alpine                 | 5432      | Secondary DB (different credentials — see `omnibot-db-pg-super-credentials` memory) |
| redis        | redis:7-alpine                     | 6380      | TLS mode on by default; drop `--tls-*` flags for plain mode |
| clamav       | clamav/clamav:stable_base          | 3310      | Antivirus scanner for media uploads |
| otel         | otel/opentelemetry-collector-contrib | 4317/4318 | OTLP gRPC + HTTP receivers |
| prometheus   | prom/prometheus:latest             | 9090      | Metrics scraping |
| grafana      | grafana/grafana:latest             | 3000      | Dashboards (default admin/admin) |

---

## 5. Configure Environment

```bash
cp .env.example .env
# Edit .env: at minimum set OPENAI_API_KEY, JWT_SECRET_KEY, M2M_SECRET_KEY,
#            DATABASE_URL, REDIS_URL to match docker-compose credentials.
```

Default dev credentials (from `docker-compose.yml`):

- **pg-super** (5433): `omnibot` / `dev_only_change_me_pg` / db `omnibot`
- **db** (5432): see `.env.example` for the alternate credentials
- **redis** (6380): password `dev_only_change_me_redis`, TLS required

Required env keys (full list in `.env.example`):

| Group | Keys |
|-------|------|
| LLM | `OPENAI_API_KEY`, `MINIMAX_API_KEY`, `GEMINI_API_KEY`, `FALLBACK_LLM_MODEL` |
| DB | `DATABASE_URL` |
| Redis | `REDIS_URL` (use `rediss://` for TLS, `redis://` for plain) |
| ClamAV | `CLAMAV_HOST`, `CLAMAV_PORT` |
| Security | `JWT_SECRET_KEY`, `M2M_SECRET_KEY`, `IP_WHITELIST_CIDRS`, `OMNIBOT_ADMIN_USER`, `OMNIBOT_ADMIN_PASS` |
| Webhooks | `MESSENGER_VERIFY_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, `A2A_JWKS_URL`, `A2A_AUDIENCE` |
| Observability | `OTEL_EXPORTER_OTLP_ENDPOINT`, `PROMETHEUS_PORT` |

The pre-push **config-liveness** preflight fails if any key used in code is
absent from `.env.example` — keep the example file in sync.

---

## 6. Run Database Migrations

```bash
# Apply Alembic migrations to pg-super
.venv/bin/python -m alembic upgrade head

# Verify schema
.venv/bin/python -m alembic current
```

---

## 7. Start the Application

```bash
# Method A: console script (installed by pip install -e .)
omnibot                                           # uses uvicorn:run

# Method B: direct uvicorn (more control)
.venv/bin/python -m uvicorn app.api.main:build_app \
  --factory --host 0.0.0.0 --port 8000 --reload

# Health check
curl http://127.0.0.1:8000/api/v1/health
# Expected: {"status": "ok"}
```

The app factory `build_app()` is in `03-development/src/app/api/main.py`. It
wires the FR-24 middleware chain (TLS → IP → Signature → Parse → Rate → RBAC),
mounts the webhook router, and mounts the Agent Card sub-app at `/.well-known/`.

---

## 8. Run Tests

```bash
# Full suite (unit + integration + e2e)
.venv/bin/python -m pytest                              # uses setup.cfg + pyproject.toml

# Unit only (fast, no infra needed)
.venv/bin/python -m pytest -m "not integration and not slow"

# Coverage
.venv/bin/python -m pytest --cov=app --cov-report=term-missing
```

Test layout:

```
03-development/tests/
├── unit/                   # FR-tagged tests (test_frNN_*.py)
├── integration/            # requires running infra
├── e2e/                    # full-stack scenarios
├── load/                   # k6 / locust scripts
├── conftest.py             # shared fixtures
├── strategy.py             # pyramid strategy config
└── pyramid.py              # test pyramid enforcement
```

JS/TS test titles must follow `it('test_frNN_xxx')` for spec-coverage matching.

---

## 9. Lint, Type-check, Mutation

```bash
# Lint
.venv/bin/python -m ruff check 03-development/src
.venv/bin/python -m ruff format --check 03-development/src

# Type check
.venv/bin/python -m pyright 03-development/src
.venv/bin/python -m mypy 03-development/src

# Mutation testing (config in setup.cfg [mutmut])
.venv/bin/python -m mutmut run
.venv/bin/python -m mutmut results
```

`pyproject.toml` excludes `harness/`, `.sessi-work/`, `tests/`, `docs/`, `.claude/`
from lint/type targets. Edit the relevant `[tool.*]` section if your workflow differs.

---

## 10. Architecture at a Glance

```
app/
├── api/        # FastAPI routes, webhooks, agent card (api_layer_no_business_logic)
├── core/       # Domain logic (paladin, knowledge, dst, emotion, api_response)
├── services/   # LLM judge, AEE adapters (a2a/cli/mcp), media, ab_testing
├── infra/      # Redis streams, rate limit, jobs, circuit breaker, alert rules
├── middleware/ # FR-24 chain (TLS → IP → Signature → Parse → Rate → RBAC)
└── admin/      # WebUI (depends on PostgreSQL via app.admin.rbac)
```

Architecture constraints (enforced by `harness detect-arch-violations`):

- **no_circular_dependencies**
- **api_layer_no_business_logic** — `app/api/*.py` only wires routers; logic lives in `core/`
- **infra_layer_no_domain_imports** — `app/infra/*` cannot import from `app/core/*`
- **paladin_executes_before_pii** — PII decryption is downstream of PALADIN
- **knowledge_query_after_dst_slot_resolution** — DST must resolve slots before knowledge lookup
- **api_layer_can_import_core_dataclasses_only** — API can import core types but not core functions

High-risk modules (extra scrutiny in review): `app.core.paladin`, `app.core.knowledge`,
`app.core.dst`, `app.infra.circuit_breaker`, `app.infra.redis_streams`,
`app.infra.rate_limit`, `app.infra.jobs`, `app.services.aee`, `app.services.llm_judge`,
`app.services.media`.

---

## 11. The Harness Workflow (Why `harness_cli.py` Is in the Repo)

`harness_cli.py` at repo root is an **auto-generated entry-point delegate** to
`harness/harness_cli.py` (the actual implementation lives in the submodule).
It exists so `.audit/` and `.methodology/` docs can reference `./harness_cli.py`
without depending on submodule path layout. Regenerate with `init-project`.

```bash
# Rebuild traceability attestation (required before push)
.venv/bin/python harness_cli.py build-trace-attestation --project . --write

# Run a per-FR Gate 1 validation
.venv/bin/python harness_cli.py run-gate --gate 1 --phase 8 --project . --fr-id FR-73
```

**Important**: harness_cli refuses system Python 3.9. Always use
`.venv/bin/python` (3.11). See `omnibot-harness-cli-python` memory.

**Architecture amendment BLOCK**: any new module under `app/` requires
`SAB.json` / `SAD.md` amendment PR before Gate 1 can run. See
`run-gate-arch-amendment-block` memory.

---

## 12. Common Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `harness_cli.py` exits with `Python 3.9 not supported` | Ran with system Python | Use `.venv/bin/python harness_cli.py …` |
| `uv sync --extra dev` fails on `gitleaks` | Dev extras pin a non-PyPI binary | `brew install gitleaks` and use plain `uv sync` |
| Pre-push hook blocks with SHA mismatch | Code changed but attestation not rebuilt | `.venv/bin/python harness_cli.py build-trace-attestation --project . --write && git add .methodology/trace && git commit --amend --no-edit` |
| `pg_isready` to `127.0.0.1:5432` fails | You're hitting `db` instead of `pg-super` (5433) | `DATABASE_URL` must point to port **5433** for `pg-super` |
| Redis TLS handshake error | Missing certs in `deployment/redis/tls/` | Generate certs as in §4, or remove `--tls-*` flags from compose for plain mode |
| New module import error after adding file | `app.<new>` not in SAD | Open architecture amendment PR first |

---

## 13. Where to Look Next

- `PROJECT_BRIEF.md` — Business KPIs, functional scope
- `SPEC.md` — Source specification (v8.1)
- `HANDOVER.md` — Session handover (FSM state, last gate, last FR)
- `.methodology/phase8_plan.md` — Active phase plan
- `02-architecture/SAD.md` — Software architecture document
- `02-architecture/TEST_SPEC.md` — Test specification
- `01-requirements/SRS.md` — Software requirements specification
- `01-requirements/TRACEABILITY_MATRIX.md` — FR ↔ test ↔ code mapping
- `CLAUDE.md` — Project-specific instructions for AI agents

---

*Last updated: 2026-06-27 — covers repo state at commit `ef32371` (post round-6 cleanup).*