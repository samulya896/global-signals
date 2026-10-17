# Global Signals — Final Audit Report

**Audit date:** 2026-10-17
**Repository:** existing `C:\Users\samul\Desktop\Trading Bot` checkout
**Scope:** current React/FastAPI app, user isolation, paper accounting, read-only market-data adapters, tests, SQLite migrations, dependency checks, and checked-in deployment files. No hosted deployment or live provider call was made.
**Trading restriction:** the application has no broker integration. Every order path writes only to a virtual portfolio denominated in INR.

## Executive result

The local app now has NSE/BSE and FX market selection, normalized provider quote/candle APIs, an account-scoped watchlist, a shared INR paper ledger, explicit instrument mention news rules, an opt-in development worker, and a user-data historical replay flow. Automated tests verify local and mocked paths. Provider credentials, subscriptions, historical data authenticity and rights, real market responses, PostgreSQL, and hosted deployments remain unverified. The project is not ready for production market use.

## Verified features

| Area | Verified result |
| --- | --- |
| Frontend | React/TypeScript SPA with authentication, dashboard, provider-aware NSE/BSE and FX workspace, quote provenance and timestamp display, candle chart, account watchlist, shared paper order form, news, strategy, and status pages. Production TypeScript check and Vite build pass. |
| Authentication | Registration/login/logout, Argon2id password hashes, opaque server-side sessions, HttpOnly cookies, production Secure flag, SameSite=Lax, CSRF checks, rate limits, revocation, account deletion, and authenticated market endpoints. API-flow tests passed. |
| User isolation | Portfolios, orders, strategy versions, and watchlists are scoped to the signed-in account. Tests cover a second account and cross-account watchlist deletion. |
| Database | SQLAlchemy models and Alembic migrations cover users, sessions, virtual portfolios, positions, orders, snapshots, audit events, strategy versions/executions, and watchlists. Fresh SQLite migration reached `c03abc12cf5e (head)`. A legacy SQLite upgrade preserved/backfilled existing position and order data. |
| Paper simulator | Long-only virtual equity and FX orders, INR cash/exposure accounting, quote-currency conversion, separate fee/slippage rates, fresh quote checks, order limits, idempotency, transaction rollback, position sizing, realized/unrealized P&L, portfolio reset, and audit events. FX tests use mocked EUR/USD and USD/INR quotes. |
| Market data | Normalized, read-only Upstox equity and Twelve Data FX adapters with backend-only auth headers, local rate limits, bounded retries, caching, timestamp/status checks, OHLC validation, and safe errors. Tests use mocked payloads only. Development synthetic equity quotes remain clearly marked and unavailable in production. |
| News and strategy | NewsAPI adapter remains optional. Signals require an explicit supported index, equity, or FX pair mention plus directional terms; conflicting direction returns HOLD. The preview is read-only. Signal source reliability is `unrated`; rules are not predictive or investment advice. |
| Worker | Separately runnable, default-off, development-only worker uses the paper simulator. It has event deduplication/recovery, confidence and freshness thresholds, cooldown, daily realized-loss limit, position/exposure limits, kill switch, weekday FX schedule, and weekday NSE hours. The NSE schedule does not include holidays. |
| Backtest | `POST /api/v1/backtest/replay` accepts a bounded rights-attested historical JSON dataset. The UI uploads it and charts the returned replay. Signals are observed at or after publication and can fill only at a later matching candle open. Virtual fees, slippage, INR conversion, long-only accounting, position/exposure/order limits, cooldown, and daily realized-loss control are applied. It does not use a live provider, persist uploaded data, or change the user's account portfolio. Tests cover next-open timing, no-fill history endings, fees/slippage, realized P&L, missing FX conversion, daily-loss limits, schema validation, auth/CSRF, file-size limits, and strategy-version ownership. |
| Deployment files | `frontend/vercel.json` parses as JSON; `render.yaml` parses as YAML and declares a Render API/PostgreSQL blueprint. Blueprint defaults keep market authorization false, strategy execution off, production paper orders off, and the simulator kill switch on. No hosting account was contacted. |
| Secret handling | `.env` was not directly inspected, modified, printed, or committed. `git check-ignore .env` confirmed the ignore rule; `git ls-files .env` returned no tracked file. API status responses do not return provider credential values. Provider test tokens were fixture strings only. |

## Checks and actual results

The Python HTTP API suite was run with permission to use a local loopback socket because Windows `TestClient` cannot start its asyncio portal inside the sandbox. Tests use isolated SQLite and mocked providers; they do not call external market or news APIs.

| Check | Result |
| --- | --- |
| Backend service, simulator, worker, market-data, signal, cookie-security, migration, and historical-replay tests | **53 passed** |
| FastAPI API-flow tests | **10 passed** — authentication, CSRF, idempotency, user isolation, production guards, watchlist isolation, and replay endpoint checks |
| Backend pytest cases collected and run in the two passing groups | **63 passed** (53 service/unit tests + 10 API-flow tests) |
| Legacy `unittest discover` | **10 tests OK** |
| `ruff check backend` | **Passed; no findings** |
| Frontend Vitest | **4 passed** |
| Frontend production build | **Passed:** `tsc -b` strict TypeScript check and Vite production bundle |
| `pip check` | **Passed; no broken requirements** |
| `npm audit --audit-level=moderate` | **Passed; 0 vulnerabilities** |
| `pip-audit --local` | **No known vulnerabilities in audited third-party packages.** The editable local project was skipped because `global-signals-api` is not published on PyPI. |
| Fresh Alembic SQLite upgrade | **Passed:** `c03abc12cf5e (head)` in the earlier migration audit; the current migration tests also passed (no migration files changed for replay) |
| Legacy-data Alembic upgrade test | **Passed:** old equity position/order currency and INR values were backfilled; watchlist table was created |
| Vercel JSON / Render YAML parsing | **Passed** |
| `git diff --check` | **Passed**; Git reported only the expected LF-to-CRLF normalization warning for `README.md` |

Frontend tests cover API request behavior and article-link safety. There is no browser end-to-end suite. Python mypy/pyright is not configured or claimed as run; the frontend type check is part of its production build.

## Security and accounting findings

- API keys are sent in backend authorization headers and are not placed in URL parameters or frontend `VITE_*` variables. Error responses are generic and do not include provider payloads or credentials.
- The `.env.example` authorization flags are operator attestations. They do not validate an API token, subscription, or display license. Keep them false until the current provider terms and the intended display use have been verified.
- Quote status is recalculated after cache hits. Orders fail closed on missing, delayed, stale, future, or inconsistent conversion quotes. Equity fills require a normal open exchange state; FX portfolio values and trade limits are converted to INR.
- Replay uploads require authentication, CSRF, a rights checkbox/attestation, a 5 MB streaming request limit, bounded row counts, and a process-local five-per-minute replay limit. User data is not written to the database; saved strategy versions are selected only within the signed-in user's scope. Returned trade and decision rows are bounded while metric counts remain totals.
- Historical replay assumes the supplied timestamps, bars, and conversions are authentic. It marks open positions at the last close and does not force-liquidate positions or subtract hypothetical final exit costs. Use data with permitted collection/replay rights and include any required `CURRENCY/INR` conversion candles.
- FX provider data is a composite midpoint and does not include bid/ask spread. Paper fills apply configured slippage and fees to that midpoint; this does not model actual FX liquidity.
- Idempotency is scoped to the user's portfolio. SQLite writes are serialized; database concurrency behavior has not been tested against PostgreSQL.
- The worker's loss cap uses realized sell P&L only and does not include intraday mark-to-market losses. Its NSE weekday time window has no holiday calendar. The worker remains development-only.
- The rate limiter is process-local. Before horizontal scaling, use a shared store or gateway limiter. Render currently specifies one Uvicorn worker, but that does not coordinate separate service instances.
- Password-reset email delivery and email verification are not implemented. The API reports password reset as unavailable rather than claiming to send mail.

## Unverified and incomplete

- No live Upstox or Twelve Data credentials were exercised. No account entitlement, data-display permission, FX redistribution rights, live quote freshness, or provider-specific rate-limit behavior was verified. No live news provider call was made.
- No licensed historical dataset was supplied or independently verified. Replay code was tested with explicit local fixtures only; timestamp authenticity, adjustments, completeness, survivorship bias, source terms, provider behavior, and any data-display license remain unverified.
- PostgreSQL migration/runtime behavior has not been verified. Only isolated SQLite migrations and tests ran.
- Vercel and Render files were syntax-checked but were not applied. Domains, TLS, environment secrets, billing plans, database backups, hosted smoke checks, and deployment rollback were not verified.
- No production worker path exists. The worker exits outside `APP_ENV=development`.
- News sentiment is a hand-maintained keyword heuristic with unrated sources. It can miss context, negation, sarcasm, ambiguity, or instrument mapping; it is not a reliable investment decision system.

## Deployment readiness

**Local learning:** ready with Python, Node.js, SQLite, synthetic equity data, and user-supplied historical replay datasets. FX and real exchange data require separately authorized provider access.
**Hosted staging:** configuration is prepared but untested. Use same-site custom domains for the Vercel frontend and Render API so session cookies work. Create disposable test accounts and verify isolation after deployment.
**Production:** **not ready.** Leave `PAPER_TRADING_ENABLED=false`, `SIMULATOR_KILL_SWITCH=true`, `STRATEGY_EXECUTION_ENABLED=false`, and both market-data display-authorization flags false until provider terms, credentials, market-data behavior, operational controls, PostgreSQL, and hosted staging have been reviewed. The app still cannot submit a real-money order.

## Exact local setup and checks

From the repository root in Windows PowerShell. The copy command preserves an existing `.env`:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m alembic -c backend/alembic.ini upgrade head
```

Start the API:

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload
```

In another terminal, start the frontend:

```powershell
cd frontend
npm ci
npm run dev
```

Run checks from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest backend -q --basetemp=.pytest-run
.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -v
.venv\Scripts\python.exe -m ruff check backend
.venv\Scripts\python.exe -m pip check
```

Run frontend checks from `frontend/`:

```powershell
npm test -- --run
npm run build
npm audit --audit-level=moderate
```

## Manual deployment steps

1. Create a Render Blueprint from the repository root and review the selected PostgreSQL plan. Keep the Blueprint's kill switch and production paper-order flags unchanged.
2. Set `FRONTEND_ORIGINS` to the exact HTTPS frontend origin. Create a Vercel project with root directory `frontend`, install command `npm ci`, build command `npm run build`, output `dist`, and a public `VITE_API_BASE_URL` pointing to the API hostname.
3. For cookie sessions, configure app/API custom domains under the same registrable domain, such as `app.example.com` and `api.example.com`.
4. Keep provider credentials in Render's backend secret settings only. Verify account terms and display rights before changing any market authorization flag. The current adapter tests are mocked and do not establish live readiness.
5. Verify `/api/v1/health` and `/api/v1/ready`, then test registration, login/logout, paper order isolation, and a second account using disposable data. Do not deploy a worker; its production path is disabled.

See [deployment.md](deployment.md) for full Vercel, Render, provider, worker, and backup instructions. The hosted services and live providers remain manual operator steps.
