# Global Signals

Global Signals is an educational news and paper-trading simulator. It combines a React/TypeScript dashboard with a FastAPI service, persistent virtual portfolios, and a rule-based news signal view. All order execution is simulated with virtual INR. There is no broker integration or real-money trading path.

## Architecture

| Path | Purpose |
| --- | --- |
| `frontend/src/App.tsx` | Dashboard pages, sign-in flow, NSE/BSE and FX market workspace, watchlist, shared INR paper order form, news, strategy, and settings. |
| `frontend/src/lib/api.ts` | Typed browser API calls, CSRF header handling, and INR formatting. |
| `frontend/src/styles.css` | Responsive dashboard styling. |
| `frontend/vite.config.ts` | Vite development server and `/api` proxy to FastAPI. |
| `backend/main.py` | FastAPI app, API routes, middleware, health/readiness checks, and frontend static serving. |
| `backend/market_data.py` | Normalized, read-only Upstox equity and Twelve Data FX adapters, timestamp/freshness checks, caching, and development-only synthetic equity quotes. |
| `backend/auth_api.py`, `backend/security.py` | Registration/login/logout, Argon2 password hashes, opaque server-side sessions, and CSRF protection. |
| `backend/models.py`, `backend/database.py` | SQLAlchemy models, SQLite development database, and configurable database connection. |
| `backend/migrations/` | Alembic schema migrations. |
| `backend/paper.py` | Persistent virtual order execution, fees/slippage, validation, idempotency, audit events, and portfolio snapshots. |
| `backend/backtest.py` | In-memory replay of rights-attested historical candles/news, next-candle-open virtual fills, costs, and risk checks. |
| `backend/strategy_engine.py`, `backend/worker.py` | Versioned news rules and an opt-in development worker that can submit only virtual orders. |
| `backend/simulator.py` | Deterministic synthetic INR equity quotes for local learning. Its synthetic backtest helper is not exposed as a genuine historical backtest. |
| `backend/news.py`, `backend/signals.py` | Optional attributed NewsAPI retrieval and explainable keyword-based signals. No sample headlines are invented. |
| `backend/tests/`, `backend/test_main.py` | Service, API-flow, simulator, configuration, news, and worker tests. |
| `frontend/src/lib/api.test.ts` | Browser API and external-link safety tests. |
| `.env.example`, `.gitignore` | Safe configuration template and secret/generated-file exclusions. |

## What works today

- React dashboard with authenticated NSE/BSE and FX search, quote provenance and timestamps, historical candle chart, account-scoped watchlist, paper trading, news, settings, and strategy views.
- Email/password registration and login; passwords are hashed with Argon2id. Sessions are stored server-side and use HttpOnly cookies; state-changing requests validate a CSRF token.
- SQLite persistence and Alembic migrations for accounts, paper portfolios, orders, audit events, per-user strategy versions, and worker idempotency records.
- Long-only simulated equity and FX orders sharing one INR ledger, with quote-currency conversion, fees, slippage, cash/exposure limits, per-order value limits, freshness checks, and idempotency keys.
- Versioned per-user strategy settings, read-only news previews, and an opt-in worker that checks event freshness, confidence, position/exposure caps, cooldown, realized daily loss, weekday IST market hours, and duplicate events before using the paper simulator.
- Account-specific portfolios and order history, explicit portfolio reset, and account deletion.
- Optional NewsAPI article retrieval with provider/source attribution, timestamps, timeouts, bounded retries, and short-lived caching. Rule signals require an explicit supported instrument mention and explain matched directional language.
- Read-only provider adapters for Upstox Analytics Tokens (NSE/BSE) and Twelve Data (FX midpoint data). Both are disabled until backend credentials and separate display authorization flags are set. Adapters are verified with mocked responses only; live accounts, credentials, entitlements, and returned data have not been tested.
- Deterministic synthetic equity quotes are available only in local development and are clearly labeled. They can be used to learn the paper ledger without provider access.
- Historical replay accepts a user-supplied JSON dataset at `POST /api/v1/backtest/replay`. News is observed only at or after its publication timestamp, fills use a later matching candle open, and the result remains separate from the saved paper portfolio. See [docs/BACKTEST_DATA_FORMAT.md](docs/BACKTEST_DATA_FORMAT.md) for the input contract and replay assumptions.

## Current limits

- Synthetic prices are hardcoded demonstrations, not exchange quotes. Live quote/candle APIs remain unverified until authorized credentials and display rights are configured. FX prices are composite midpoint data without provider bid/ask spread.
- Backtest results are only as reliable as the uploaded data and its original timestamps. The application requires a rights attestation but cannot independently verify data accuracy, licensing, completeness, adjustments, or survivorship bias. The simple keyword strategy also remains an unrated heuristic.
- Production synthetic prices are disabled. Production paper orders remain disabled unless `PAPER_TRADING_ENABLED=true`; the global kill switch in `render.yaml` is also on by default. No broker adapter or real order path exists.
- Password-reset email delivery is not implemented. The API explicitly returns an unavailable response rather than claiming to send email.
- The strategy worker is development-only, explicitly opt-in, and globally kill-switchable. It uses explicit instrument mentions, shares simulator INR conversion/risk accounting, observes NSE weekday session hours and FX weekday availability, and refuses to execute outside `APP_ENV=development`. Its news source reliability is not rated, its NSE session has no exchange-holiday calendar, and its daily loss check uses realized sell P&L only, not intraday mark-to-market losses.
- There is no email verification, password-reset delivery, verified provider entitlement, or production worker deployment. News classification is an unrated explainable heuristic, not investment advice.
- Frontend API tests and backend API-flow tests exist; there is no browser end-to-end suite.
- The rate limiter is in-process. A deployed multi-worker service needs a shared limiter at the gateway or another shared store.
- PostgreSQL is supported by configuration and an optional driver extra, but has not been deployment-tested here. SQLite is the tested local database.
- NewsAPI access requires an appropriate plan. The Developer plan is restricted to development/testing; configure an authorized plan before any production use. See [NewsAPI authentication](https://newsapi.org/docs/authentication) and [NewsAPI terms](https://newsapi.org/terms). `NEWSAPI_PRODUCTION_AUTHORIZED=true` is an operator attestation flag, not automatic license verification.

## Local setup (Windows PowerShell)

Use Python 3.11+ and Node.js 20.19+ or 22.12+.

From the repository root:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "backend[dev]"
python -m alembic -c backend/alembic.ini upgrade head
```

If `.env` does not exist, copy `.env.example` to `.env`; otherwise edit only the specific values you need. The project loads `.env` on the backend only. Keep real credentials in `.env`; it is ignored by Git. Never put API keys in frontend variables or commit them.

Start the API in one terminal:

```powershell
python -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. The Vite server proxies `/api` requests to FastAPI at `127.0.0.1:8000`. FastAPI serves the built React app from `frontend/dist` after a production frontend build. API docs are at <http://127.0.0.1:8000/docs>; health and readiness are `/api/v1/health` and `/api/v1/ready`.

To build the dashboard bundle:

```powershell
cd frontend
npm run build
```

## How to try paper trading

1. Start the API and frontend as above, then register a local account in the dashboard.
2. Open **Paper Trading**. The account starts with virtual INR 100,000 by default.
3. In development, choose one of the labeled synthetic instruments (`NIFTYBEES`, `BANKBEES`, `ITBEES`, `GOLDBEES`) and submit a small buy order. Provider-listed NSE/BSE and FX instruments need authorized backend credentials and display permission first.
4. Confirm that the order appears in recent orders, virtual INR cash changes, and a holding appears. The quote source is labeled synthetic or provider-attributed.
5. Try a sell order up to the held quantity. Selling more than the virtual position, exceeding limits, or repeating a request with the same idempotency key is rejected or safely deduplicated.
6. Use the explicit reset control to restore the virtual account. Reset removes its simulated orders and positions and returns cash to the starting balance.

All order endpoints only update the local virtual portfolio. No broker credentials or real orders are supported.

## Historical replay

The Backtesting page accepts a historical JSON dataset containing OHLC candles and archived, timezone-aware news publication times. The API enforces a 5 MB request limit and bounds the number of candles and news rows. The page asks for a data-rights attestation before submitting the replay. Results are calculated in memory, use virtual INR only, and do not update saved positions or orders. A provider credential is not needed to replay an uploaded dataset.

The replay observes an article at the first candle timestamp at or after publication and can fill only at a later matching bar's open. It applies configured virtual fees, slippage, position and exposure caps, order-value limits, cooldown, daily realized-loss checks, and long-only rules. Non-INR forex pairs require included direct or inverse INR conversion candles. The result retains the strategy version used and marks open positions at the last available close; it does not force-liquidate them.

Use only historical data whose collection and replay are permitted. See [docs/BACKTEST_DATA_FORMAT.md](docs/BACKTEST_DATA_FORMAT.md). `GET /api/v1/backtest` continues to return an unavailable response because it has no dataset to replay; the authenticated upload flow uses `POST /api/v1/backtest/replay`.

## Optional development strategy worker

The separate worker is disabled by default. It needs a NewsAPI key and an enabled per-user strategy, and it runs only with `APP_ENV=development` through the simulator. It can use synthetic equity quotes or explicitly authorized read-only provider data. Use only a disposable local database; never point it at production data. News source reliability is not independently rated.

Set `STRATEGY_EXECUTION_ENABLED=true` and `SIMULATOR_KILL_SWITCH=false` in `.env`, then enable and save the strategy in Strategy Lab. Start the API, frontend, and worker in separate terminals. From the repository root, run:

```powershell
.venv\Scripts\Activate.ps1
python -m backend.worker
```

The worker evaluates equity signals on weekdays during 09:15–15:30 IST and FX signals on weekdays. The NSE session check does not include exchange holidays. Set `SIMULATOR_KILL_SWITCH=true` to stop all new manual and worker orders; the switch is read dynamically. Production worker execution exits without submitting orders.

## Tests and checks

From the repository root, with the virtual environment active:

```powershell
python -m pytest backend -q --basetemp=.pytest-run
python -m unittest discover -s backend -p "test_*.py" -v
python -m ruff check backend
```

Frontend type-check and production bundle:

```powershell
cd frontend
npm test
npm run build
npm audit --audit-level=moderate
```

The Python tests use temporary SQLite databases and mocked/local provider inputs; they do not call a broker or external market/news provider. Ruff checks syntax and common Python errors. The frontend build runs strict TypeScript checks and creates the Vite production bundle. Vitest tests browser API requests and article URL safety. No hosted deployment or browser end-to-end test is included.

## Main API routes

All current frontend requests use `/api/v1`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health`, `/api/v1/ready` | Process and database checks. |
| `GET` | `/api/v1/auth/csrf` | Initialize or retrieve a browser CSRF token. |
| `POST` | `/api/v1/auth/register`, `/login`, `/logout` | Create an account and manage a session. |
| `GET` | `/api/v1/auth/me` | Current signed-in account. |
| `DELETE` | `/api/v1/auth/me` | Delete the signed-in account after password confirmation. |
| `POST` | `/api/v1/auth/password-reset` | Explicitly unavailable until email delivery is implemented. |
| `GET` | `/api/v1/news`, `/news/{category}`, `/news/live`, `/news/status` | News provider status and optional articles. |
| `GET` | `/api/v1/signals` | Explainable signals from available live news. |
| `GET` | `/api/v1/market` | Local demo equity quotes; unavailable in production unless a configured provider is authorized. |
| `GET` | `/api/v1/markets/status`, `/markets/instruments`, `/markets/quote`, `/markets/candles` | Authenticated normalized read-only NSE/BSE and FX data, when backend providers and display authorization are configured. |
| `GET`, `POST`, `DELETE` | `/api/v1/watchlist` | Authenticated, CSRF-protected and account-scoped market watchlist. |
| `GET` | `/api/v1/portfolio`, `/portfolio/history`, `/performance` | Signed-in virtual account state. |
| `POST` | `/api/v1/trades` | Signed-in simulated order; requires CSRF and `Idempotency-Key`. |
| `POST` | `/api/v1/portfolio/reset` | Reset the signed-in virtual account with an exact confirmation phrase. |
| `GET` | `/api/v1/backtest?days=90` | Explicitly unavailable; no default or generated history is used. |
| `POST` | `/api/v1/backtest/replay` | Authenticated and CSRF-protected in-memory replay of a rights-attested user dataset; never changes saved portfolio state. |
| `GET`, `PUT` | `/api/v1/strategy/config`, `/api/v1/strategy/versions` | Authenticated, CSRF-protected strategy settings and version history. |
| `POST` | `/api/v1/strategy/preview` | Read-only news rule evaluation; never creates orders. |

Legacy `/api/...` aliases remain for the original dashboard and tests.

## Configuration

See `.env.example` for the available variables. Keep `APP_ENV=development` for local synthetic quotes and paper simulation. `UPSTOX_ANALYTICS_TOKEN` and `TWELVEDATA_API_KEY` stay on the backend; the corresponding authorization variables are operator attestations, not license verification. FX data is a composite midpoint and does not include provider bid/ask spread. Use a durable database URL and HTTPS termination for any deployment. Production paper orders default to disabled, and the app has no real-order route.

The Vercel frontend can set `VITE_API_BASE_URL` to a public API hostname; this is not a secret. Production cookie authentication requires the app and API to use same-site custom domains and the API's exact HTTPS origin in `FRONTEND_ORIGINS`. Never put provider or database secrets in a `VITE_*` variable.

Deployment configuration and exact Vercel/Render setup steps are in [docs/deployment.md](docs/deployment.md). The project has not been deployed or verified on those services. Provider adapters exist, but credentials, data rights, PostgreSQL, and hosted behavior remain unverified.
