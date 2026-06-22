#!/usr/bin/env python3
"""
Krypto Steuer-Kurs-Fetcher
--------------------------
Lädt historische Tageskurse (EUR) von CoinGecko für die in einer Excel-Datei
angegebenen Coins und Zeiträume.

Ausgabe pro Coin:
  • CSV  „{SYMBOL} - Kurse - {Durchschnitt}.csv"  (tägliche Schlusskurse)
  • PNG  „{SYMBOL}_{Start}_{Ende}_screenshot.png"  (CoinMarketCap-Screenshot)

Verwendung:
  python main.py eingabe.xlsx [--output-dir ./output] [--no-screenshots]

Excel-Format (Spaltenköpfe exakt so):
  | Coin | Start Date | End Date |
  | ETH  | 2025-01-01 | 2025-12-31 |
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from api import resolve_coin, fetch_daily_prices, set_api_key
from screenshot import take_price_screenshot


def _german_number(value: float) -> str:
    """Format float in German style: 1.234,56"""
    us = f"{value:,.2f}"           # → "1,234.56"
    return us.replace(",", "X").replace(".", ",").replace("X", ".")


def process_coin(row: pd.Series, output_dir: Path, do_screenshots: bool, log: logging.Logger):
    coin_input  = str(row["Coin"]).strip()
    start_date  = pd.to_datetime(row["Start Date"]).date()
    end_date    = pd.to_datetime(row["End Date"]).date()

    log.info(f"Verarbeite {coin_input}  ({start_date} – {end_date})")

    # --- Resolve coin identity ---
    coin_info    = resolve_coin(coin_input)
    symbol       = coin_info["symbol"]
    gecko_id     = coin_info["coingecko_id"]
    cmc_slug     = coin_info["cmc_slug"]
    log.info(f"  → {symbol}  (CoinGecko: {gecko_id})")

    # --- Fetch daily prices ---
    prices = fetch_daily_prices(gecko_id, start_date, end_date)
    if prices.empty:
        raise ValueError("Keine Tageskurse empfangen.")

    avg_eur = prices["Kurs (EUR)"].mean()
    log.info(f"  → {len(prices)} Tage  |  Ø {avg_eur:.4f} EUR")

    # --- Save CSV (German format: semicolon separator, comma decimal) ---
    prices["Datum"] = prices["Datum"].apply(
        lambda d: d.strftime("%d.%m.%Y")
    )
    avg_str  = _german_number(avg_eur)
    csv_name = f"{symbol} - Kurse - {avg_str}.csv"
    csv_path = output_dir / csv_name
    prices.to_csv(csv_path, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    log.info(f"  → CSV: {csv_name}")

    # --- Screenshot ---
    if do_screenshots:
        png_name = f"{symbol}_{start_date}_{end_date}_screenshot.png"
        png_path = output_dir / png_name
        take_price_screenshot(cmc_slug, start_date, end_date, str(png_path))
        log.info(f"  → PNG: {png_name}")


def main():
    parser = argparse.ArgumentParser(
        description="Lädt historische Krypto-Tageskurse (EUR) von CoinGecko.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("excel_file", help="Pfad zur Excel-Eingabedatei")
    parser.add_argument(
        "--output-dir", default="output",
        help="Ausgabeverzeichnis (Standard: ./output)"
    )
    parser.add_argument(
        "--no-screenshots", action="store_true",
        help="Browser-Screenshots überspringen (schneller)"
    )
    parser.add_argument(
        "--api-key", metavar="CG-xxxx",
        help=(
            "CoinGecko Demo API-Key (kostenlos auf coingecko.com/api).\n"
            "Alternativ: Umgebungsvariable COINGECKO_API_KEY setzen."
        ),
    )
    args = parser.parse_args()

    if args.api_key:
        set_api_key(args.api_key)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Logging: Konsole + errors.log
    log = logging.getLogger("fetcher")
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    fh = logging.FileHandler(output_dir / "errors.log", encoding="utf-8")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(fmt)
    log.addHandler(ch)
    log.addHandler(fh)

    # Read input Excel
    try:
        df = pd.read_excel(args.excel_file)
    except Exception as exc:
        print(f"Fehler: Excel-Datei konnte nicht gelesen werden – {exc}")
        sys.exit(1)

    required = {"Coin", "Start Date", "End Date"}
    missing  = required - set(df.columns)
    if missing:
        print(f"Fehler: Fehlende Spalten in der Excel-Datei: {missing}")
        print(f"Vorhandene Spalten: {list(df.columns)}")
        print("Erwartet: Coin | Start Date | End Date")
        sys.exit(1)

    errors = []
    for i, row in df.iterrows():
        try:
            process_coin(row, output_dir, not args.no_screenshots, log)
        except Exception as exc:
            coin_label = str(row.get("Coin", f"Zeile {i+2}"))
            log.warning(f"  ✗ {coin_label}: {exc}")
            errors.append(f"{coin_label}: {exc}")

    print("\n" + "=" * 55)
    print(f"Fertig! Ausgabe: {output_dir.resolve()}")
    if errors:
        print(f"\n{len(errors)} Fehler (siehe auch errors.log):")
        for e in errors:
            print(f"  • {e}")
    else:
        print("Alle Coins erfolgreich verarbeitet.")


if __name__ == "__main__":
    main()
