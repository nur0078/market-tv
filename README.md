# market-tv

A trading-floor TV dashboard for **Fixed Income & Equities** desks. It's a single `index.html` with no build step, no API keys and no server. Host it on GitHub Pages and point the TV's browser at it.

## Where the data comes from

All market data comes from **TradingView's free embeddable widgets**. Nothing on the page is simulated.

| Panel | Source | Freshness |
|-------|--------|-----------|
| FX strip (AUD/USD, AUD/JPY, USD/JPY, EUR/USD, AUD/NZD) | `FX:` | Real-time |
| Gold, Brent, WTI, copper | `OANDA:` / `TVC:` CFDs | Streaming (broker/CFD prices) |
| Australia 200 chart, global indices | `OANDA:` index CFDs | Streaming. Indicative CFD prices, **not** the official index |
| Govt yields, AU vs US 10Y chart, 2Y "front end" charts | `TVC:` yields | Streaming |
| ASX 200 heatmap | ASX via TradingView | **Delayed** (exchange rules) |
| Event calendar, RBA/Fed rates & votes | Hand-entered in `CONFIG` | Update after each meeting |

TradingView's widget FAQ says exchanges require websites to pay for real-time data, so widgets stream **delayed** exchange data, while **forex and crypto are real-time**. That's why the index panels use broker CFD prices. They track the market live but aren't the official exchange print.

The free widgets are licensed with TradingView branding ("Charts & quotes by TradingView" in the footer). TradingView's general terms restrict commercial use without a separate agreement, so check with compliance / market data before putting this on a commercial floor.

## Run it

1. Merge this PR, then **Settings → Pages → Deploy from branch → `main` / root**.
2. Open the Pages URL on the TV and press **F** for fullscreen.

It scales from 1080p to 4K. Below 1180px wide it reflows into a scrolling page.

## Panels

| # | Panel | Contents |
|---|-------|----------|
| 01 | **Next on the tape** | Split-flap countdown to the next high-impact release + the next four events (AEDT) |
| 02 | **Policy & the front end** | RBA & Fed rate, last move and vote, days to next meeting, plus a live 2Y yield chart for each (market pricing of the path) |
| 03 | **Australia 200 intraday** | 5-minute area chart |
| 04 | **Curves & spreads** | AU/US/DE/JP govt yield quotes + AU 10Y vs US 10Y chart |
| 05 | **Indices & vol** | Australia 200, US 500, US Tech 100, Japan 225, HK 33, Euro 50, UK 100, VIX, DXY |
| 06 | **ASX 200 heatmap** | By sector, sized by market cap, coloured by % change |
| — | FX & commodities strip | Live tickers |
| — | Coming up wire | Auto-generated from the calendar, so it never goes stale |

The header shows session status (ASX / LDN / NYSE open, pre-open, closing auction) plus an **ONLINE / OFFLINE · DATA STALE** indicator. Widgets silently freeze if the network drops, and the board re-embeds them when the connection returns.

## URL options

| Param | Effect |
|-------|--------|
| `?view=fi` / `?view=eq` / `?view=all` | Layout preset per desk (press **V** to cycle) |
| `?desk=Sydney%20Markets` | Desk name in the header |

## Changing symbols

Everything is in `CONFIG.symbols` at the top of the script, in TradingView's `EXCHANGE:TICKER` format. If a widget shows *"This symbol is only available on TradingView"*, TradingView isn't licensed to show that symbol in widgets. Swap it for another source (e.g. `PEPPERSTONE:AUS200` instead of `OANDA:AU200AUD`).

## Maintenance

- **After each RBA / Fed meeting:** update `CONFIG.policy` (rate, last move, vote, next date).
- **Monthly:** extend `CONFIG.events` (times in UTC).
- **TV housekeeping:** 1–2px burn-in shift every 2 min, full reload every 6h, cursor hides after 3s.
