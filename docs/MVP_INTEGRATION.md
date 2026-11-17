# Integrating the local MVP

Goal: **one** TradeMind AI codebase. The MVP that exists only on the owner's Windows machine
(`TradeMind_AI_MVP_v2\trademind-ai-mvp`) is brought into this repository and folded into the
existing modules. It does not run as a second application, and the Risk Engine, Paper Broker and
strategy code are never duplicated.

## Branches

| Branch | Purpose | Merge |
|---|---|---|
| `main` | Released code | — |
| `hoplite/vps-vercel-deploy` (PR #2) | Vercel + VPS deployment, dashboard | Owner decides; not auto-merged |
| `hoplite/vps-vercel-deploy--mvp-integration` | MVP import + porting, built on PR #2 | After PR #2; retarget its PR to `main` then |

The integration branch is based on PR #2 so the frontend and deployment files are already present.
The import only adds `legacy/mvp/**` and `docs/MVP_INTEGRATION_REPORT.md`, so it cannot overwrite them.

## Step 1 — import (Windows PowerShell, ~5 minutes)

Prerequisites: Git for Windows, Python 3.12 (`py -3.12`). Run in a **new** folder, not inside the MVP folder.

```powershell
# One-time: clone (skip if you already have the repository; then just `cd` into it and `git fetch origin`)
cd $HOME\Documents
git clone https://github.com/jalal-stack/nq.git trademind
cd trademind

# Switch to the integration branch
git fetch origin
git switch hoplite/vps-vercel-deploy--mvp-integration

# Create .venv for the conflict analyzer (frontend install is part of setup; it is harmless here)
# If scripts are blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\dev.ps1 setup

# Import. Use the real path of your extracted folder.
.\scripts\import_mvp.ps1 -Source "C:\Users\<you>\Downloads\TradeMind_AI_MVP_v2\trademind-ai-mvp"

# Check what changed: only legacy/mvp/** and docs/MVP_INTEGRATION_REPORT.md
git status

git add legacy/mvp docs/MVP_INTEGRATION_REPORT.md
git commit -m "Import local MVP into legacy/mvp (quarantined, not wired in)"
git push origin hoplite/vps-vercel-deploy--mvp-integration
```

What `import_mvp.ps1` does:

- refuses to run unless the current branch is `hoplite/vps-vercel-deploy--mvp-integration`;
- accepts either the outer `TradeMind_AI_MVP_v2` folder or the inner `trademind-ai-mvp` folder;
- copies into `legacy/mvp/` only, and refuses to overwrite an earlier import without `-Force`;
- **does not copy** `.env` / `.env.*` (except `.env.example`), `.venv`, `__pycache__`, `.pytest_cache`,
  `node_modules`, `*.db` / `*.sqlite*`, `*.log`, `*.pem` / `*.key`, `Dockerfile`, `docker-compose*.yml`;
- scans for API keys, passwords and private keys **before copying anything** and stops if it finds one;
- writes `legacy/mvp/IMPORT_MANIFEST.txt` (relative paths, SHA-256 hashes, list of skipped files; no
  absolute paths or user names);
- runs `scripts/mvp_audit.py`, which reads the code without executing it, and writes
  `docs/MVP_INTEGRATION_REPORT.md`.

If the secret scan stops the import, replace the value in the MVP folder with a placeholder, put the
real value in your local `.env` (which is never copied), and run the import again.
BLOCKER findings in the report (for example a `create_order` call) do not stop the import. Commit them:
they sit in quarantine and are removed during porting.

## Step 2 — conflicts identified before merging

`docs/MVP_INTEGRATION_REPORT.md` lists the exact conflicts found in your code. These are already known
from the MVP layout and the two codebases:

### File and path collisions (why the MVP is not copied over `backend/`)

| MVP path | Collides with | Resolution |
|---|---|---|
| `backend/app/` | `backend/trademind/` | Port module by module (table below); `app` package is not kept |
| `backend/requirements.txt` | `backend/pyproject.toml` | Merge missing deps (SQLAlchemy, psycopg, redis, alembic) into `pyproject.toml` |
| `backend/pytest.ini` | `[tool.pytest.ini_options]` in `pyproject.toml` | `pytest.ini` would take precedence and break test discovery; drop it |
| `backend/tests/` | `backend/tests/` | Port the 3 Risk Engine tests to target `RiskEngine` |
| `backend/Dockerfile`, `docker-compose.yml` | Docker is not allowed | Not imported |
| `.env.example`, `README.md` | Same files at repo root | Merge keys under the `TRADEMIND_` prefix; keep the current README |
| `migrations/001_init.sql` | — (no database yet) | Becomes the Alembic baseline after the fixes below |

### Module mapping (no duplicate implementations)

| MVP module | Canonical home | Action |
|---|---|---|
| `app/risk.py` | `trademind/risk/engine.py` `RiskEngine` | Add any MVP rule missing from the engine as a new `CheckCode`; delete the MVP module |
| `app/paper.py` | `trademind/execution/paper.py` `PaperBroker` | Keep the MVP proposal → approval flow, executed by `PaperBroker`; delete any live path |
| `app/strategy.py` | `trademind/backtest/engine.py` (`Strategy` protocol) + `trademind/indicators.py` | MVP EMA/RSI/ATR becomes a `Strategy` using shared indicators; compare signals on the same data |
| `app/market_data.py` | `trademind/data/providers.py` + `data/validation.py` | Merge provider options into the existing CCXT/yfinance adapters |
| `app/config.py` | `trademind/config.py` | Add DB/Redis settings; paper-only validator stays |
| `app/main.py` | `trademind/api/main.py` (`/api/v1` router) | Port MVP-only routes onto the existing router |
| `app/schemas.py` | `trademind/domain.py`, risk/engine models | Reuse existing models; add only what is missing |
| `app/db.py`, `app/models.py`, `app/seed.py` | new `trademind/db/` | Adopt MVP tables with the fixes below |

### API

- `GET /api/v1/health` exists in both. The canonical endpoint stays and returns a superset of the MVP fields
  (it already returns `mode: "paper_only"` and `live_execution_enabled: false`), so existing clients keep working.
- Every other MVP route is ported onto the canonical router and calls the canonical services.
- Route-level collisions and MVP-only routes are listed per path in the report.

### Database schema

The report checks the SQL migration against the SQLAlchemy models and the canonical domain types.
Expected fixes:

- **Money and quantity columns** use `NUMERIC`, not `FLOAT`/`REAL`/`DOUBLE PRECISION`. The Risk Engine sizes
  positions with `Decimal`.
- **Timestamps** use `TIMESTAMPTZ` / `DateTime(timezone=True)`, because all canonical timestamps are UTC-aware.
- **Enum values** match `trademind.domain`:
  - side: `buy` / `sell` (lower-case);
  - order status: `pending`, `partially_filled`, `filled`, `cancelled`, `rejected`, `expired`;
  - asset class: `crypto` / `stock` / `forex`.
- **Drift**: every table in the SQL migration needs a model, and every column must have the same type in both.

## Step 3 — porting (done on the integration branch after your push)

1. Run the report on your real code and pin the findings in the integration PR.
2. Persistence: `trademind/db/` (SQLAlchemy 2 models, session) and an Alembic baseline migration with the
   schema fixes, plus PostgreSQL/Redis settings (`TRADEMIND_DATABASE_URL`, `TRADEMIND_REDIS_URL`).
3. Risk: diff MVP rules against `RiskEngine`, add missing checks, and port the 3 MVP risk tests.
4. Proposals and approvals: MVP proposal flow → `RiskEngine` → user approval → `PaperBroker`, stored in the DB.
5. Strategy and market data merged into the existing modules.
6. API routes ported; the dashboard gets the proposal queue and portfolio views.
7. Delete `legacy/mvp/`. Every step keeps CI green.

## Safety rules that do not change

- `TRADEMIND_TRADING_MODE` accepts only `paper`; there is no live-execution code path.
- `backend/tests/test_mvp_import_tooling.py::test_canonical_code_has_no_live_trading_paths` scans all shipped code
  for order submission, transaction signing, key material and `live_execution_enabled = True`.
  Ported code that trips it fails CI.
- The deterministic Risk Engine is the only gate before paper execution; no agent or MVP rule can bypass a rejection.
- Nothing from `legacy/` is imported, packaged or deployed.
