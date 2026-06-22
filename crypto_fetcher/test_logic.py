"""Unit tests for api.py and main.py logic – runs without network access."""

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import api
from main import _german_number, process_coin


class TestGermanNumber(unittest.TestCase):
    def test_small(self):
        self.assertEqual(_german_number(1.23), "1,23")

    def test_thousands(self):
        self.assertEqual(_german_number(2341.87), "2.341,87")

    def test_large(self):
        self.assertEqual(_german_number(52341.50), "52.341,50")

    def test_zero_cents(self):
        self.assertEqual(_german_number(100.0), "100,00")


class TestResolveCoин(unittest.TestCase):
    def test_known_symbol(self):
        info = api.resolve_coin("ETH")
        self.assertEqual(info["symbol"], "ETH")
        self.assertEqual(info["coingecko_id"], "ethereum")

    def test_case_insensitive(self):
        self.assertEqual(api.resolve_coin("ada")["symbol"], "ADA")

    def test_full_name(self):
        self.assertEqual(api.resolve_coin("CARDANO")["symbol"], "ADA")

    def test_unknown_falls_back_to_search(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "coins": [{"id": "mytoken", "symbol": "MTK", "name": "MyToken"}]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            info = api.resolve_coin("mytoken")
        self.assertEqual(info["symbol"], "MTK")
        self.assertEqual(info["coingecko_id"], "mytoken")


class TestFetchDailyPrices(unittest.TestCase):
    def _make_mock(self, prices_list):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"prices": prices_list}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_daily_granularity(self):
        """For >90-day ranges CoinGecko returns one point per day."""
        import time as _time
        from datetime import datetime

        start = date(2025, 1, 1)
        end   = date(2025, 1, 5)

        prices = []
        for i in range(5):
            d = date(2025, 1, i + 1)
            ts_ms = int(datetime.combine(d, datetime.min.time()).timestamp()) * 1000
            prices.append([ts_ms, float(2000 + i)])

        with patch("requests.get", return_value=self._make_mock(prices)):
            df = api.fetch_daily_prices("ethereum", start, end)

        self.assertEqual(len(df), 5)
        self.assertAlmostEqual(df["Kurs (EUR)"].iloc[0], 2000.0)
        self.assertAlmostEqual(df["Kurs (EUR)"].iloc[4], 2004.0)

    def test_hourly_aggregated_to_daily(self):
        """For ≤90-day ranges CoinGecko returns hourly; we take last per day."""
        from datetime import datetime

        start = date(2025, 6, 1)
        end   = date(2025, 6, 2)

        prices = []
        for day_offset in range(2):
            for hour in range(24):
                d = datetime(2025, 6, 1 + day_offset, hour, 0)
                ts_ms = int(d.timestamp()) * 1000
                prices.append([ts_ms, float(1800 + day_offset * 100 + hour)])

        with patch("requests.get", return_value=self._make_mock(prices)):
            df = api.fetch_daily_prices("ethereum", start, end)

        self.assertEqual(len(df), 2)
        # Last hour of day 0 (hour 23) → 1800 + 0*100 + 23 = 1823
        self.assertAlmostEqual(df["Kurs (EUR)"].iloc[0], 1823.0)
        # Last hour of day 1 (hour 23) → 1800 + 1*100 + 23 = 1923
        self.assertAlmostEqual(df["Kurs (EUR)"].iloc[1], 1923.0)

    def test_date_range_clipped(self):
        """Prices outside the requested range are dropped."""
        from datetime import datetime

        start = date(2025, 3, 2)
        end   = date(2025, 3, 3)

        prices = []
        for day_offset in range(5):  # days 1–5 March
            d = date(2025, 3, 1 + day_offset)
            ts_ms = int(datetime.combine(d, datetime.min.time()).timestamp()) * 1000
            prices.append([ts_ms, float(1500 + day_offset)])

        with patch("requests.get", return_value=self._make_mock(prices)):
            df = api.fetch_daily_prices("ethereum", start, end)

        self.assertEqual(len(df), 2)
        self.assertEqual(df["Datum"].iloc[0], date(2025, 3, 2))
        self.assertEqual(df["Datum"].iloc[1], date(2025, 3, 3))


class TestProcessCoin(unittest.TestCase):
    def test_csv_filename_and_content(self):
        """process_coin writes correctly named CSV with German decimal format."""
        import tempfile
        from datetime import datetime

        start = date(2025, 1, 1)
        end   = date(2025, 1, 3)

        # Mock: 3 daily prices → average = (1.0 + 2.0 + 3.0) / 3 = 2.0
        prices_raw = []
        for i in range(3):
            d = date(2025, 1, 1 + i)
            ts_ms = int(datetime(2025, 1, 1 + i).timestamp()) * 1000
            prices_raw.append([ts_ms, float(i + 1)])

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"prices": prices_raw}
        mock_resp.raise_for_status = MagicMock()

        row = pd.Series({
            "Coin": "ETH",
            "Start Date": str(start),
            "End Date": str(end),
        })

        import logging
        log = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch("requests.get", return_value=mock_resp):
                process_coin(row, out, do_screenshots=False, log=log)

            csvs = list(out.glob("*.csv"))
            self.assertEqual(len(csvs), 1)
            # Average of 1.0, 2.0, 3.0 = 2.0 → "2,00" in German
            self.assertIn("2,00", csvs[0].name)
            self.assertTrue(csvs[0].name.startswith("ETH - Kurse - "))

            content = csvs[0].read_text(encoding="utf-8-sig")
            lines = [l for l in content.splitlines() if l.strip()]
            self.assertEqual(lines[0], "Datum;Kurs (EUR)")
            self.assertEqual(len(lines), 4)  # header + 3 data rows


if __name__ == "__main__":
    unittest.main(verbosity=2)
