"""CoinGecko API wrapper: coin resolution and historical price fetching.

Requires a free CoinGecko Demo API key.
Get yours (free, no payment) at: https://www.coingecko.com/en/api
Set via environment variable:  export COINGECKO_API_KEY=CG-xxxxxxxxxxxxxxxx
Or pass --api-key to main.py.
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, date

BASE_URL = "https://api.coingecko.com/api/v3"

# Static mapping: uppercase symbol/name → CoinGecko ID + CMC slug + display symbol
COIN_MAPPING: dict[str, dict] = {
    "BTC":       {"coingecko_id": "bitcoin",            "cmc_slug": "bitcoin",       "symbol": "BTC"},
    "BITCOIN":   {"coingecko_id": "bitcoin",            "cmc_slug": "bitcoin",       "symbol": "BTC"},
    "ETH":       {"coingecko_id": "ethereum",           "cmc_slug": "ethereum",      "symbol": "ETH"},
    "ETHEREUM":  {"coingecko_id": "ethereum",           "cmc_slug": "ethereum",      "symbol": "ETH"},
    "ADA":       {"coingecko_id": "cardano",            "cmc_slug": "cardano",       "symbol": "ADA"},
    "CARDANO":   {"coingecko_id": "cardano",            "cmc_slug": "cardano",       "symbol": "ADA"},
    "ATOM":      {"coingecko_id": "cosmos",             "cmc_slug": "cosmos",        "symbol": "ATOM"},
    "COSMOS":    {"coingecko_id": "cosmos",             "cmc_slug": "cosmos",        "symbol": "ATOM"},
    "SOL":       {"coingecko_id": "solana",             "cmc_slug": "solana",        "symbol": "SOL"},
    "SOLANA":    {"coingecko_id": "solana",             "cmc_slug": "solana",        "symbol": "SOL"},
    "DOT":       {"coingecko_id": "polkadot",           "cmc_slug": "polkadot",      "symbol": "DOT"},
    "POLKADOT":  {"coingecko_id": "polkadot",           "cmc_slug": "polkadot",      "symbol": "DOT"},
    "MATIC":     {"coingecko_id": "matic-network",      "cmc_slug": "polygon",       "symbol": "MATIC"},
    "POL":       {"coingecko_id": "matic-network",      "cmc_slug": "polygon",       "symbol": "POL"},
    "POLYGON":   {"coingecko_id": "matic-network",      "cmc_slug": "polygon",       "symbol": "MATIC"},
    "LINK":      {"coingecko_id": "chainlink",          "cmc_slug": "chainlink",     "symbol": "LINK"},
    "CHAINLINK": {"coingecko_id": "chainlink",          "cmc_slug": "chainlink",     "symbol": "LINK"},
    "XRP":       {"coingecko_id": "ripple",             "cmc_slug": "xrp",           "symbol": "XRP"},
    "RIPPLE":    {"coingecko_id": "ripple",             "cmc_slug": "xrp",           "symbol": "XRP"},
    "DOGE":      {"coingecko_id": "dogecoin",           "cmc_slug": "dogecoin",      "symbol": "DOGE"},
    "DOGECOIN":  {"coingecko_id": "dogecoin",           "cmc_slug": "dogecoin",      "symbol": "DOGE"},
    "AVAX":      {"coingecko_id": "avalanche-2",        "cmc_slug": "avalanche",     "symbol": "AVAX"},
    "AVALANCHE": {"coingecko_id": "avalanche-2",        "cmc_slug": "avalanche",     "symbol": "AVAX"},
    "UNI":       {"coingecko_id": "uniswap",            "cmc_slug": "uniswap",       "symbol": "UNI"},
    "UNISWAP":   {"coingecko_id": "uniswap",            "cmc_slug": "uniswap",       "symbol": "UNI"},
    "LTC":       {"coingecko_id": "litecoin",           "cmc_slug": "litecoin",      "symbol": "LTC"},
    "LITECOIN":  {"coingecko_id": "litecoin",           "cmc_slug": "litecoin",      "symbol": "LTC"},
    "XLM":       {"coingecko_id": "stellar",            "cmc_slug": "stellar",       "symbol": "XLM"},
    "STELLAR":   {"coingecko_id": "stellar",            "cmc_slug": "stellar",       "symbol": "XLM"},
    "ALGO":      {"coingecko_id": "algorand",           "cmc_slug": "algorand",      "symbol": "ALGO"},
    "ALGORAND":  {"coingecko_id": "algorand",           "cmc_slug": "algorand",      "symbol": "ALGO"},
    "FIL":       {"coingecko_id": "filecoin",           "cmc_slug": "filecoin",      "symbol": "FIL"},
    "FILECOIN":  {"coingecko_id": "filecoin",           "cmc_slug": "filecoin",      "symbol": "FIL"},
    "NEAR":      {"coingecko_id": "near",               "cmc_slug": "near-protocol", "symbol": "NEAR"},
    "VET":       {"coingecko_id": "vechain",            "cmc_slug": "vechain",       "symbol": "VET"},
    "VECHAIN":   {"coingecko_id": "vechain",            "cmc_slug": "vechain",       "symbol": "VET"},
    "OSMO":      {"coingecko_id": "osmosis",            "cmc_slug": "osmosis",       "symbol": "OSMO"},
    "OSMOSIS":   {"coingecko_id": "osmosis",            "cmc_slug": "osmosis",       "symbol": "OSMO"},
    "INJ":       {"coingecko_id": "injective-protocol", "cmc_slug": "injective",     "symbol": "INJ"},
    "INJECTIVE": {"coingecko_id": "injective-protocol", "cmc_slug": "injective",     "symbol": "INJ"},
    "KAVA":      {"coingecko_id": "kava",               "cmc_slug": "kava",          "symbol": "KAVA"},
    "BAND":      {"coingecko_id": "band-protocol",      "cmc_slug": "band-protocol", "symbol": "BAND"},
    "JUNO":      {"coingecko_id": "juno-network",       "cmc_slug": "juno",          "symbol": "JUNO"},
    "STRD":      {"coingecko_id": "stride",             "cmc_slug": "stride",        "symbol": "STRD"},
    "STRIDE":    {"coingecko_id": "stride",             "cmc_slug": "stride",        "symbol": "STRD"},
}

_API_KEY: str | None = None


def set_api_key(key: str | None) -> None:
    """Set the CoinGecko Demo API key (overrides COINGECKO_API_KEY env var)."""
    global _API_KEY
    _API_KEY = key


def _headers() -> dict:
    key = _API_KEY or os.environ.get("COINGECKO_API_KEY")
    h = {"User-Agent": "Mozilla/5.0 (compatible; crypto-tax-fetcher/1.0)"}
    if key:
        h["x-cg-demo-api-key"] = key
    return h


def _get(url: str, params: dict = None, retries: int = 3) -> dict:
    """GET with exponential back-off on 429; raises descriptive error on 403."""
    delay = 1.5
    for attempt in range(retries):
        time.sleep(delay)
        resp = requests.get(url, params=params, headers=_headers(), timeout=30)

        if resp.status_code == 429:
            wait = delay * (2 ** attempt)
            print(f"  Rate-limit (429) – warte {wait:.0f}s …")
            time.sleep(wait)
            continue

        if resp.status_code == 403:
            raise PermissionError(
                "CoinGecko API: Zugriff verweigert (HTTP 403).\n"
                "Ein kostenloser Demo-API-Key ist erforderlich.\n"
                "  1. Registrieren auf https://www.coingecko.com/en/api (kostenlos)\n"
                "  2. API-Key kopieren (Format: CG-xxxxxxxxxxxxxxxx)\n"
                "  3. Beim Start übergeben:  python main.py eingabe.xlsx --api-key CG-xxxx\n"
                "     Oder als Umgebungsvariable:  export COINGECKO_API_KEY=CG-xxxx"
            )

        resp.raise_for_status()
        return resp.json()

    resp.raise_for_status()


def resolve_coin(coin_input: str) -> dict:
    """Return {'coingecko_id', 'cmc_slug', 'symbol'} for a coin symbol/name/ID."""
    key = coin_input.upper().strip()
    if key in COIN_MAPPING:
        return COIN_MAPPING[key]

    data = _get(f"{BASE_URL}/search", params={"query": coin_input})
    coins = data.get("coins", [])
    if not coins:
        raise ValueError(
            f"Coin '{coin_input}' auf CoinGecko nicht gefunden.\n"
            f"Bekannte Kürzel: {', '.join(sorted(k for k in COIN_MAPPING if len(k) <= 5))}"
        )
    best = coins[0]
    return {
        "coingecko_id": best["id"],
        "cmc_slug":     best["id"],
        "symbol":       best["symbol"].upper(),
    }


def fetch_daily_prices(coingecko_id: str, start_date: date, end_date: date) -> pd.DataFrame:
    """
    Fetch EUR closing prices from CoinGecko for each calendar day in [start_date, end_date].
    Returns DataFrame with columns: Datum (date), Kurs (EUR) (float).
    """
    from_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    to_ts   = int(datetime.combine(end_date,   datetime.max.time()).timestamp())

    data = _get(
        f"{BASE_URL}/coins/{coingecko_id}/market_chart/range",
        params={"vs_currency": "eur", "from": from_ts, "to": to_ts},
    )

    if not data.get("prices"):
        raise ValueError(
            f"CoinGecko lieferte keine Preisdaten für '{coingecko_id}' "
            f"im Zeitraum {start_date} – {end_date}."
        )

    df = pd.DataFrame(data["prices"], columns=["ts_ms", "price"])
    df["Datum"] = pd.to_datetime(df["ts_ms"], unit="ms").dt.date

    # One closing price per calendar day (handles both hourly and daily granularity)
    daily = (
        df.groupby("Datum")["price"]
        .last()
        .reset_index()
        .rename(columns={"price": "Kurs (EUR)"})
    )

    # Clip to exact requested range
    daily = daily[
        (daily["Datum"] >= start_date) & (daily["Datum"] <= end_date)
    ].sort_values("Datum").reset_index(drop=True)

    return daily
