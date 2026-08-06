import unittest
import pandas as pd
import numpy as np
import sys
import os

# Ensure we import the correct module from web_dashboard, avoiding root conflicts
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scoring_engine import apply_weighted_scoring

class TestScoringEngine(unittest.TestCase):
    
    def test_bayesian_analyst_adjustment(self):
        data = {
            "Ticker": ["STOCK_A", "STOCK_B", "STOCK_C"],
            "Industry": ["Tech", "Tech", "Tech"],
            "Analyst Rating": [5.0, 4.5, 3.0],
            "Total Analysts": [1.0, 20.0, 5.0]
        }
        df = pd.DataFrame(data)
        result_df = apply_weighted_scoring(df)
        
        score_a = result_df.loc[result_df["Ticker"] == "STOCK_A", "Adjusted Analyst Rating"].iloc[0]
        score_b = result_df.loc[result_df["Ticker"] == "STOCK_B", "Adjusted Analyst Rating"].iloc[0]
        
        self.assertGreater(
            score_b, score_a, 
            f"Expected Stock B ({score_b:.2f}) to have a better adjusted rating than Stock A ({score_a:.2f})"
        )
        
        total_a = result_df.loc[result_df["Ticker"] == "STOCK_A", "Total Value Score"].iloc[0]
        total_b = result_df.loc[result_df["Ticker"] == "STOCK_B", "Total Value Score"].iloc[0]
        self.assertGreater(
            total_b, total_a,
            "Expected Stock B to have a better Total Value Score than Stock A"
        )

    def test_pert_expected_upside_and_risk_spread(self):
        data = {
            "Ticker": ["STOCK_1", "STOCK_2", "STOCK_3"],
            "Industry": ["Tech", "Tech", "Tech"],
            "Worst Case": [10.0, np.nan, 5.0],
            "Probable Case": [20.0, 30.0, 10.0],
            "Best Case": [40.0, np.nan, 20.0]
        }
        df = pd.DataFrame(data)
        result_df = apply_weighted_scoring(df)
        
        upside_1 = result_df.loc[result_df["Ticker"] == "STOCK_1", "Expected Upside"].iloc[0]
        self.assertAlmostEqual(upside_1, (10 + 4*20 + 40)/6)
        
        risk_1 = result_df.loc[result_df["Ticker"] == "STOCK_1", "Risk Spread"].iloc[0]
        self.assertEqual(risk_1, 30.0)
        
        upside_2 = result_df.loc[result_df["Ticker"] == "STOCK_2", "Expected Upside"].iloc[0]
        self.assertEqual(upside_2, 30.0)
        
        risk_2 = result_df.loc[result_df["Ticker"] == "STOCK_2", "Risk Spread"].iloc[0]
        self.assertTrue(np.isnan(risk_2))

    def test_target_metric_ranking(self):
        data = {
            "Ticker": ["STOCK_15", "STOCK_10", "STOCK_30"],
            "Industry": ["Tech", "Tech", "Tech"],
            "P/E": [15.0, 10.0, 30.0]
        }
        df = pd.DataFrame(data)
        result_df = apply_weighted_scoring(df)
        
        score_15 = result_df.loc[result_df["Ticker"] == "STOCK_15", "Total Value Score"].iloc[0]
        score_10 = result_df.loc[result_df["Ticker"] == "STOCK_10", "Total Value Score"].iloc[0]
        score_30 = result_df.loc[result_df["Ticker"] == "STOCK_30", "Total Value Score"].iloc[0]
        
        self.assertGreater(score_15, score_10)
        self.assertGreater(score_10, score_30)

    def test_data_completeness_penalty(self):
        data = {
            "Ticker": ["FULL", "MISSING"],
            "Industry": ["Tech", "Tech"],
            "PEG": [1.0, np.nan],
            "P/E": [15.0, 15.0],
            "EPS": [2.0, np.nan]
        }
        df = pd.DataFrame(data)
        result_df = apply_weighted_scoring(df)
        
        comp_full = result_df.loc[result_df["Ticker"] == "FULL", "Data Completeness %"].iloc[0]
        comp_miss = result_df.loc[result_df["Ticker"] == "MISSING", "Data Completeness %"].iloc[0]
        self.assertGreater(comp_full, comp_miss)
        
        score_full = result_df.loc[result_df["Ticker"] == "FULL", "Total Value Score"].iloc[0]
        score_miss = result_df.loc[result_df["Ticker"] == "MISSING", "Total Value Score"].iloc[0]
        self.assertGreater(score_full, score_miss)

if __name__ == '__main__':
    unittest.main()
