import unittest
import pandas as pd
import numpy as np

# Import the extracted utils for the scraper logic
from scraper_utils import (
    build_rankings_by_date, 
    _normalize_series, 
    _calc_composite_for_group, 
    format_rank_change
)

class TestScraperJsonLogic(unittest.TestCase):
    
    def test_format_rank_change(self):
        # Positive rank change (previous rank was higher number = worse)
        self.assertEqual(format_rank_change(1, 3), '↑ 2')
        # Negative rank change (previous rank was lower number = better)
        self.assertEqual(format_rank_change(5, 4), '↓ 1')
        # No change
        self.assertEqual(format_rank_change(2, 2), '-')
        # Missing previous rank
        self.assertEqual(format_rank_change(10, np.nan), '-')

    def test_normalize_series(self):
        # Standard normalization: 10, 20, 30.
        # Max is 30 (100%), Min is 10 (0%)
        s1 = pd.Series([10, 20, 30])
        # By default clip_pct is (5, 95), so min and max might be clipped slightly.
        # Let's test with clip_pct=(0, 100) to ensure exact values
        res1 = _normalize_series(s1, clip_pct=(0, 100))
        self.assertAlmostEqual(res1.iloc[0], 0.0)
        self.assertAlmostEqual(res1.iloc[1], 50.0)
        self.assertAlmostEqual(res1.iloc[2], 100.0)

        # Inverted normalization (e.g. Risk Spread, lower is better)
        res_inv = _normalize_series(s1, invert=True, clip_pct=(0, 100))
        self.assertAlmostEqual(res_inv.iloc[0], 100.0)
        self.assertAlmostEqual(res_inv.iloc[1], 50.0)
        self.assertAlmostEqual(res_inv.iloc[2], 0.0)
        
    def test_calc_composite_for_group(self):
        # Test the composite scoring correctly weights the metrics
        data = {
            "Total Value Score": [100.0, 50.0],
            "Industry Value Score": [100.0, 50.0],
            "Expected Upside": [100.0, 50.0],
            "Risk Spread": [0.0, 100.0]
        }
        group = pd.DataFrame(data)
        # Because we have only 2 rows, clipping at 5-95% will bring them closer to 50
        # Let's override _normalize_series behavior implicitly by providing identical values
        # No, wait, _normalize_series scales values.
        
        # We can just check that STOCK 0 scores higher than STOCK 1
        res = _calc_composite_for_group(group)
        self.assertGreater(res.iloc[0], res.iloc[1])
        
    def test_build_rankings_by_date(self):
        data = {
            "Date": ["2026-08-01", "2026-08-01", "2026-08-02", "2026-08-02"],
            "Ticker": ["STOCK_A", "STOCK_B", "STOCK_A", "STOCK_B"],
            "⭐ Composite Score": [80.0, 90.0, 95.0, 85.0]
        }
        df = pd.DataFrame(data)
        
        rankings = build_rankings_by_date(df)
        
        # On Aug 1: STOCK_B (90) is Rank 1, STOCK_A (80) is Rank 2
        self.assertEqual(rankings["2026-08-01"]["STOCK_B"], 1)
        self.assertEqual(rankings["2026-08-01"]["STOCK_A"], 2)
        
        # On Aug 2: STOCK_A (95) is Rank 1, STOCK_B (85) is Rank 2
        self.assertEqual(rankings["2026-08-02"]["STOCK_A"], 1)
        self.assertEqual(rankings["2026-08-02"]["STOCK_B"], 2)

if __name__ == '__main__':
    unittest.main()
