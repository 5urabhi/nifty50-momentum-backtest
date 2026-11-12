"""Offline-only DhanHQ v2 adapter tests. NO TOKEN and NO NETWORK."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from index_research.dhan_data import (
    Instrument, read_instruments, date_windows, candles_to_frame,
    download_candles, save_download, build_monthly_close
)


def response(rows):
    """Two trading dates with valid Unix timestamps."""
    return {
        "timestamp":[1705289400,1705375800][:rows],
        "open":[100,110][:rows],
        "high":[110,120][:rows],
        "low":[95,105][:rows],
        "close":[105,115][:rows],
        "volume":[1000,2000][:rows],
    }


class DhanOfflineTests(unittest.TestCase):
    def test_chunk_boundaries(self):
        ranges=list(date_windows("2024-01-01","2024-08-01",90))
        self.assertEqual(ranges[0][0].isoformat(),"2024-01-01")
        self.assertEqual(ranges[-1][1].isoformat(),"2024-08-01")
        self.assertTrue(all((stop-start).days<=90 for start,stop in ranges))

    def test_bad_ohlc_is_blocked(self):
        instrument=Instrument("A","1333")
        invalid=response(2)
        invalid["high"]=[98,120]
        with self.assertRaises(ValueError):
            candles_to_frame(invalid,instrument)

    def test_mock_download_contains_no_secrets(self):
        seen=[]
        def fake_post(endpoint,payload,token):
            seen.append((endpoint,payload,token))
            return response(2)
        instrument=Instrument("A","1333")
        # timezone-verified test range covers both example timestamps.
        frame=download_candles(instrument,"2024-01-01","2024-02-01",
                               token="SECRET_TEST_TOKEN",post=fake_post,pause_seconds=0)
        self.assertEqual(len(frame),2)
        self.assertEqual(seen[0][0],"/charts/historical")
        self.assertEqual(seen[0][1]["securityId"],"1333")
        self.assertEqual(seen[0][1]["toDate"],"2024-02-01")
        with tempfile.TemporaryDirectory() as temp:
            csv_path,manifest=save_download(frame,instrument,temp,
                                            "2024-01-01","2024-02-01",None)
            self.assertTrue(csv_path.exists())
            self.assertNotIn("SECRET_TEST_TOKEN",manifest.read_text())
            self.assertNotIn("SECRET_TEST_TOKEN",csv_path.read_text())

    def test_monthly_requires_no_fabricated_benchmark(self):
        a=Instrument("A","1333")
        b=Instrument("B","1444")
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"raw"
            raw.mkdir()
            for ins in [a,b]:
                frame=candles_to_frame(response(2),ins)
                save_download(frame,ins,raw,"2024-01-01","2024-02-01",None)
            folder=Path(tmp)/"monthly"
            path=build_monthly_close(raw,[a,b],folder)
            self.assertTrue(path.exists())
            self.assertFalse((folder/"benchmark.csv").exists())
            self.assertFalse((folder/"membership.csv").exists())
            self.assertTrue((folder/"DHAN_UNADJUSTED_DATA_WARNING.txt").exists())
            values=pd.read_csv(path)
            self.assertEqual(list(values.columns),["date","A","B"])

    def test_instruments_from_local_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"instruments.csv"
            p.write_text("label,security_id,exchange_segment,instrument,expiry_code\nA,1333,NSE_EQ,EQUITY,0\n")
            instruments=read_instruments(p)
            self.assertEqual(instruments[0].security_id,"1333")
            self.assertEqual(instruments[0].exchange_segment,"NSE_EQ")

    def test_duplicate_timestamp_rejected(self):
        values=response(2)
        values["timestamp"][1]=values["timestamp"][0]
        with self.assertRaises(ValueError):
            candles_to_frame(values,Instrument("A","1333"))


if __name__=="__main__":
    unittest.main()
