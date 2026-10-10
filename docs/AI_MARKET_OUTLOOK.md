# AI Market Outlook

The outlook module publishes an immutable analysis after a candle has actually closed, then watches later closed bars against that analysis. It does not authorise trades. Qualified Gold setups are handed to the existing opportunity pipeline (P1/P2, Stage 7, Stage 8). Stage 8 remains the only place a risk approval is recorded.

## Horizons

| Horizon | Clock | Universe | What it publishes |
| --- | --- | --- | --- |
| Monthly | Finalized MN `close_time` | Scanner universe (28 FX + XAUUSD) | Strategic context for the next month. It does not cancel a valid shorter-term opportunity. |
| Weekly | Finalized W1 `close_time` | Scanner universe | Week direction, confirmed weekly fractals on the W candles, SCH in a pane under the W chart only. |
| Daily | New York 17:00 trading day, aligned to the stored D1 close when that bar is present | Scanner universe | Next session outlook for Asia, London and New York. |
| Gold H8 | Finalized XAUUSD H8 `close_time` | XAUUSD | Operational direction. M15 is the execution-confirmation timeframe. M5 is optional refinement. |

The scanner universe is the platform's 28 FX pairs plus XAUUSD. Outlook does not add instruments outside that universe.

## Scheduling

The API process runs the outlook scheduler on a timer (the same worker that already publishes the daily outlook). On Vercel, `GET /api/ai-outlook/jobs/daily` is the cron entry and is safe to call more than once. The open page may ask for a catch-up, but the job does not depend on a browser staying open.

A run's identity is the horizon plus the broker close timestamp (`W1|…`, `MN|…`, `H8|…`). Daily keeps the trading date so existing outlooks stay addressable. Creating the same key again does not start a second analysis. A failed run retries until the next candle of that horizon; after a restart the same row is picked up again. Missed closes are recovered newest first, one close per horizon per pass, so the current week, month and H8 session publish before older gaps. Only that latest close sends an alert. Older recovered closes stay in history and do not notify again.

When monthly, weekly, daily and H8 closes fall inside the close grace window, one snapshot is frozen and the horizons run in that order: Monthly, Weekly, Daily, H8. Each horizon keeps its own close timestamp. Bars that opened at or after that horizon's close are dropped, so a shared snapshot cannot see the next period.

## After publication

The original payload is not updated. Monitoring writes revisions:

`PUBLISHED → WATCHING → APPROACHING_ZONE → ZONE_REACHED → REACTION_PENDING → CONFIRMATION_PENDING → AUTHORIZATION_PENDING`

Terminal states are `INVALIDATED`, `EXPIRED`, `COMPLETED` and `NO_OPPORTUNITY`. `AUTHORIZED` is written only when the autonomous engine has already stored a `RISK_APPROVED` opportunity for that symbol. The outlook never submits an order and never changes risk limits.

Between H8 closes, every new closed H1 and M15 bar is compared with the published Gold outlook. An M15 rejection inside the ERZ can reach confirmation before the next H8 close. It still waits for the H1 confirmation sequence before `AUTHORIZATION_PENDING`.

The evidence score is the alignment of closed-bar evidence from 0 to 100. It is not a win probability. Historical hit rate, MFE and MAE are stored separately when the next period has closed.

## API

Authenticated readers use the existing `/api/ai-outlook` routes. `horizon` is `DAILY` (default), `WEEKLY`, `MONTHLY` or `H8`. `GET /status` returns the latest run of each horizon. The page polls those reads; it does not recompute the engines.
