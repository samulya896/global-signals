# Deployment guide

This repository contains deployment configuration, but no deployment has been run or verified. Use a staging environment first.

## Selected architecture

- **Vercel** serves the React/Vite frontend from `frontend/` as static assets and handles client-side routes.
- **Render** runs the FastAPI API as a persistent web service.
- **Render PostgreSQL** stores accounts, sessions, virtual portfolios, positions, orders, snapshots, audit events, strategy versions, and worker idempotency records. The database and API use the same region (Singapore) and the private database URL.
- `backend.worker` is a separate development-only paper worker. It is deliberately not declared as a production Render service because it refuses production execution. Any future worker must be separate from FastAPI and use the shared durable database.

This separates static delivery from a persistent API and database. Vercel's monorepo settings let the frontend use `frontend/` as its project root; Render's FastAPI service can build from the repository root and connect to managed PostgreSQL. The Vercel rewrite uses the documented capture-group negative-lookahead syntax to leave `/api/` requests out of the SPA fallback. See [Vercel monorepo setup](https://vercel.com/docs/monorepos), [Vercel Vite deployment](https://vercel.com/docs/frameworks/frontend/vite), [Vercel rewrite configuration](https://vercel.com/docs/project-configuration/vercel-json), [Render FastAPI deployment](https://render.com/docs/deploy-fastapi), [Render Blueprints](https://render.com/docs/blueprint-spec), and [Render PostgreSQL connections](https://render.com/docs/postgresql-creating-connecting).

## 1. Backend and database on Render

1. Push this repository to a Git provider and create a Render Blueprint from the repository root. Render reads [render.yaml](../render.yaml), which declares the API service and a private PostgreSQL database in Singapore.
2. Review the selected PostgreSQL plan and service pricing in Render before applying the Blueprint. The plan in the file is a small persistent database plan; it is not a free trial configuration.
3. Set the prompted `FRONTEND_ORIGINS` value to the exact HTTPS origin that will serve the frontend, for example `https://app.example.com`. Do not use `*`, a localhost URL, or a trailing path.
4. `NEWS_API_KEY` is optional. Enter it only in Render's backend secret settings if the provider plan permits the intended use. `NEWSAPI_PRODUCTION_AUTHORIZED` stays `false` unless the account has an appropriate production authorization. The setting is an operator attestation, not an automated license check.
5. Keep `APP_ENV=production`. The Blueprint runs migrations with `python -m alembic -c backend/alembic.ini upgrade head` before starting the API, then starts `backend.main:app` with one Uvicorn worker. `/api/v1/ready` is the service health check. The global simulator kill switch is enabled, production paper orders are disabled, and strategy execution is disabled by default in this Blueprint.

The default Render connection string is normalized by the backend to SQLAlchemy's `psycopg` dialect. The Blueprint installs `backend[postgres]`, which includes the PostgreSQL driver. Render recommends using the internal database URL for services in the same region; do not copy database credentials into frontend configuration.

If the selected Render plan does not support a pre-deploy command, run the migration as a one-off command from the repository root with the same backend environment variables before promoting the service:

```powershell
python -m alembic -c backend/alembic.ini upgrade head
```

## Read-only market-data access

The backend contains adapters for Upstox's read-only Analytics Token (NSE/BSE quotes and candles) and Twelve Data FX composite midpoint data. These adapters were tested with mocked payloads only. No provider credentials, account entitlement, license, actual market response, or production display permission was verified.

If the intended subscription permits this app's display use, add `UPSTOX_ANALYTICS_TOKEN` and `TWELVEDATA_API_KEY` only to the Render backend secret settings. Set `UPSTOX_DATA_DISPLAY_AUTHORIZED=true` or `TWELVEDATA_DISPLAY_LICENSE_AUTHORIZED=true` only after reviewing current provider terms and securing the relevant data-display rights. These booleans are operator attestations; they do not validate a license or token. The Blueprint leaves both false. Check `/api/v1/markets/status` after configuration; it reports provider configuration state and never proves a live quote is current. Inspect quote timestamps and status in the authenticated market screen.

Upstox's Analytics Token is read-only; no broker order endpoints exist in this application. Twelve Data FX records are midpoint candles without bid/ask spread. Do not treat these provider values as executable prices. `PAPER_TRADING_ENABLED` remains false and `SIMULATOR_KILL_SWITCH` remains true by default. Any paper execution still updates only a user's virtual INR ledger; the project has no path to submit a real trade.

## 2. Frontend on Vercel

Create a Vercel project from this repository and set:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework preset | Vite |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Environment Variable | `VITE_API_BASE_URL=https://api.example.com` |

Set `VITE_API_BASE_URL` for Production and Preview environments to the corresponding API hostname. This value is public and is only the API's base URL. Never place `NEWS_API_KEY`, database URLs, session keys, email credentials, or other secrets in a `VITE_*` variable.

The committed `frontend/vercel.json` rewrites frontend routes to `index.html` while excluding `/api/`. The frontend API client uses `credentials: "include"`; the FastAPI app allows credentialed CORS only for configured origins.

For cookie authentication, use custom domains under the same registrable domain, such as `app.example.com` and `api.example.com`. Configure the backend's `FRONTEND_ORIGINS` as `https://app.example.com`. The backend sets Secure, HttpOnly session cookies with SameSite=Lax in production. A default `*.vercel.app` frontend calling a `*.onrender.com` API is cross-site and is not a supported cookie-auth deployment configuration.

## 3. Separate strategy worker

### Local development

Run the worker in a third terminal from the repository root:

```powershell
.venv\Scripts\Activate.ps1
python -m backend.worker
```

It requires `APP_ENV=development`, `STRATEGY_EXECUTION_ENABLED=true`, `SIMULATOR_KILL_SWITCH=false`, an enabled saved strategy, and NewsAPI configured for permitted development/testing. Use a disposable local database. It can use synthetic equities or explicitly authorized read-only provider data. The worker writes only through the account's paper-simulator service; it has no broker adapter or order-routing client. Equity signals run on weekdays during 09:15–15:30 IST; FX signals run on weekdays. It does not know exchange holidays and source reliability is not rated.

### Hosted deployment status

Do **not** create a production Render Background Worker from this revision. `python -m backend.worker` exits without executing when `APP_ENV=production`. Do not work around that guard by setting a production service to development or by sharing the production database with a development worker.

The worker's production execution path is not implemented or tested. Keep `STRATEGY_EXECUTION_ENABLED=false` and `SIMULATOR_KILL_SWITCH=true`. Render supports background workers and Blueprint `type: worker` services. Its pre-deploy migration command runs on a separate instance from the running service, so schema changes must remain backward-compatible during rollout. Review Render's [Background Worker](https://render.com/docs/background-workers), [Blueprint](https://render.com/docs/blueprint-spec), and [pre-deploy command](https://render.com/docs/deploys) documentation before any future worker release.

## 4. Verify staging

After setting domains and environment variables, verify:

```text
https://api.example.com/api/v1/health
https://api.example.com/api/v1/ready
```

The first should return `{"status":"healthy"}`. The second should report the database as healthy. Then register a test account from the Vercel frontend, sign out and back in, and verify account isolation with a second account. Do not use real user data for staging tests.

**Production paper orders are disabled by default.** Market-data adapters exist, but provider configuration, current credentials, display rights, data freshness, and deployed behavior are unverified. The market API fails closed unless a provider key and its separate authorization attestation are set. `PAPER_TRADING_ENABLED=false` and `SIMULATOR_KILL_SWITCH=true` keep production orders unavailable by default. Historical replay accepts a user-supplied, rights-attested dataset, but the app does not verify its authenticity or license; no real historical dataset or hosted replay has been audited. Keep the app simulated; never connect a broker.

## 5. News provider setup

Keep provider credentials in the API service's secret environment. With no key, the API reports that no live feed is configured and returns no fabricated sample articles. NewsAPI's official docs recommend an API-key header, which the adapter uses. Its Developer plan is limited to development/testing; check [NewsAPI authentication](https://newsapi.org/docs/authentication), [endpoint documentation](https://newsapi.org/docs/endpoints/everything), and [terms](https://newsapi.org/terms) for current access rights before using articles outside development.

## 6. Backups and recovery

Configure managed PostgreSQL backups and retention in Render for the selected plan. For an additional manual backup, install PostgreSQL client tools and run PowerShell with `DATABASE_URL` supplied securely through the current shell environment:

```powershell
pg_dump --dbname="$env:DATABASE_URL" --format=custom --file=global-signals-backup.dump
```

Store the backup in an encrypted, access-controlled location. To verify recovery, restore into a new empty database rather than overwriting the live database:

```powershell
pg_restore --dbname="$env:RESTORE_DATABASE_URL" --no-owner --no-privileges global-signals-backup.dump
```

After restoring, point a staging API at the restored database, run `/api/v1/ready`, and verify a test account and its virtual portfolio before changing production traffic. Keep database URLs out of command output, screenshots, commits, and support tickets.

## Current deployment blockers

- Provider adapters are implemented but no live credential, entitlement, display-license, or returned market data has been verified. Production paper orders remain disabled by default.
- Historical replay is implemented and tested with explicit local fixtures. A licensed historical dataset, its timestamp authenticity, provider terms, and hosted replay behavior remain unverified. The production strategy worker path is not implemented.
- No email verification or password-reset delivery integration exists.
- Rate limiting is process-local and needs a shared gateway/store before scaling to multiple workers.
- API/DB hosting and Vercel configuration have not been deployed or smoke-tested in a hosted environment.
- The worker is implemented for opt-in development simulation only; a safe production worker path, live-provider verification, and an NSE holiday calendar are not in place.
