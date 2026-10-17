# Historical replay dataset format

The replay API accepts a JSON object with `dataset_name`, `data_rights_confirmed`, `starting_cash`, `candles`, and `news`. The browser file limit and API body limit are 5 MB. The API accepts at most 20,000 candles and 2,000 news events. The dataset is validated and replayed in memory; it is not stored in the account database.

## Required fields

| Field | Type | Rules |
| --- | --- | --- |
| `dataset_name` | string | 1–100 characters; identifies the uploaded dataset in the result. |
| `data_rights_confirmed` | `true` | Must be `true`. The user must also check the rights attestation in the UI. This is an attestation, not independent verification. |
| `strategy_version` | integer or omitted | Optional. Omit to use the latest saved strategy version for this account; use `0` for built-in defaults or an owned saved version number to reproduce that immutable configuration. |
| `starting_cash` | number | Positive virtual INR amount, at most 1,000,000,000. |
| `candles` | array | 2–20,000 OHLC bars. |
| `news` | array | 1–2,000 archived events. |

Each candle needs:

- `market_type`: `EQUITY` or `FOREX`.
- `symbol`: supported instrument name. Equity signal names must match the explicit aliases in `backend/signals.py`; forex symbols use `BASE/QUOTE`.
- `timestamp`: ISO 8601 timestamp with `Z` or an explicit UTC offset.
- `open`, `high`, `low`, and `close`: finite positive numbers. High and low must contain both open and close.
- `quote_currency`: three-letter currency. Indian equity bars must use `INR`.
- `base_currency`: required for forex and must match the pair symbol. Optional for equities.

Each news event needs:

- `title`: 1–300 characters.
- `published_at`: ISO 8601 timestamp with `Z` or an explicit UTC offset.
- Optional `description` (up to 2,000 characters), `source` (up to 120), and `url` (up to 500).

The dataset must not contain duplicate candles for the same market, symbol, and instant. Candle order in the file does not affect replay order; the server sorts timestamps. Avoid mixing adjusted and unadjusted prices or candle intervals without documenting that choice outside the dataset.

## Replay rules

1. The engine observes each news event at the first candle timestamp on or after its publication time. Events published after the last candle cannot trade.
2. An accepted signal can fill only at the open of a **later** candle for its explicitly mentioned instrument. It never fills on the candle at which the news first becomes available.
3. Fills are virtual and apply the configured equity or FX slippage and fee rates. Positions are long-only; a SELL closes held units and never opens a short.
4. The simulator uses the current account strategy settings (or defaults when no version exists), maximum INR order value, portfolio exposure cap, position cap, cooldown, and daily realized-loss limit. The strategy `enabled` switch controls the background worker; explicitly starting a replay evaluates the selected rules regardless of that switch.
5. Equity is marked at candle closes, carrying forward the last instrument close for up to seven days when its market has no candle at a shared replay timestamp. Forex quote currencies other than INR require a matching direct or inverse `CURRENCY/INR` conversion candle within 24 hours to enter or value the position. Include those conversion candles in the same dataset.
6. The request does not read live quotes, write the persistent paper portfolio, or contact a broker. It cannot place a real-money trade.

The response contains the full replay metrics and a sampled equity curve (up to 1,200 points), up to 1,000 fill rows, and up to 2,000 decision rows. Count fields remain totals when response rows are truncated. Open positions are marked to the last available close; final equity does not force-liquidate positions or deduct hypothetical exit costs. The chart and tables are summaries of the uploaded input, not proof that the data is accurate or that the strategy will perform similarly in the future.

Use only data whose collection, storage, and replay are permitted by its source and applicable terms. Preserve original publication timestamps and source attribution where available. This project does not independently verify timestamp authenticity, corporate actions, survivorship bias, data licensing, completeness, or adjustment methodology.

## Request access

Send the JSON to `POST /api/v1/backtest/replay` while signed in. The endpoint requires the session cookie and `X-CSRF-Token` header used by the frontend and allows five replay requests per minute per client address. Invalid datasets return HTTP 422; payloads over 5 MB return HTTP 413. `GET /api/v1/backtest` remains an explicit unavailable response because it has no historical dataset to replay.
