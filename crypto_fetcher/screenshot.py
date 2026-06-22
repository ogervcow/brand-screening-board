"""Full-page browser screenshot of CoinMarketCap historical price table via Playwright."""

import time
from datetime import date
from pathlib import Path


def take_price_screenshot(
    cmc_slug: str,
    start_date: date,
    end_date: date,
    output_path: str,
) -> None:
    """
    Take a full-page screenshot of the CoinMarketCap historical-data page
    for the given coin and date range, saved to output_path as PNG.

    Falls back to CoinGecko if CoinMarketCap fails.
    """
    from playwright.sync_api import sync_playwright, Error as PWError

    url_cmc = (
        f"https://coinmarketcap.com/currencies/{cmc_slug}/historical-data/"
        f"?start={start_date.strftime('%Y%m%d')}&end={end_date.strftime('%Y%m%d')}"
    )
    url_gecko = (
        f"https://www.coingecko.com/en/coins/{cmc_slug}/historical_data"
        f"?start_date={start_date}&end_date={end_date}&currency=eur"
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        success = False
        for label, url, table_selector in [
            ("CoinMarketCap", url_cmc,   "table"),
            ("CoinGecko",     url_gecko, "table"),
        ]:
            page = context.new_page()
            try:
                print(f"  Screenshot via {label}: {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=40_000)

                # Dismiss cookie/consent banners if present
                for btn_text in ["Accept All", "Accept all", "Alle akzeptieren", "I Accept", "Got it"]:
                    try:
                        btn = page.get_by_role("button", name=btn_text)
                        if btn.count():
                            btn.first.click()
                            time.sleep(1)
                            break
                    except PWError:
                        pass

                # Wait for the price table to appear
                page.wait_for_selector(table_selector, timeout=20_000)
                time.sleep(2)  # Let JS finish rendering rows

                page.screenshot(path=output_path, full_page=True)
                success = True
                break
            except Exception as exc:
                print(f"  Warnung – {label} Screenshot fehlgeschlagen: {exc}")
            finally:
                page.close()

        browser.close()

    if not success:
        raise RuntimeError(
            f"Screenshot für '{cmc_slug}' konnte weder über CoinMarketCap "
            "noch über CoinGecko erstellt werden."
        )
