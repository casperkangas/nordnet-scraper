import unittest
import pandas as pd
import numpy as np

# Import the scoring engine from the same directory
from scoring_engine import apply_weighted_scoring

class TestScoringEngine(unittest.TestCase):
    
    def test_bayesian_analyst_adjustment(self):
        # 1. Create a mock DataFrame with our edge cases
        data = {
            "Ticker": ["STOCK_A", "STOCK_B", "STOCK_C"],
            "Industry": ["Tech", "Tech", "Tech"],
            # Stock A: High rating, very low confidence (1 analyst)
            # Stock B: Good rating, very high confidence (20 analysts)
            # Stock C: Baseline dummy to stabilize averages
            "Analyst Rating": [5.0, 4.5, 3.0],
            "Total Analysts": [1.0, 20.0, 5.0]
        }
        df = pd.DataFrame(data)
        
        # 2. Run the scoring engine
        result_df = apply_weighted_scoring(df)
        
        # 3. Extract the scores
        score_a = result_df.loc[result_df["Ticker"] == "STOCK_A", "Adjusted Analyst Rating"].iloc[0]
        score_b = result_df.loc[result_df["Ticker"] == "STOCK_B", "Adjusted Analyst Rating"].iloc[0]
        
        # 4. Verify that Stock B's adjusted rating is higher than Stock A's
        self.assertGreater(
            score_b, score_a, 
            f"Expected Stock B ({score_b:.2f}) to have a better adjusted rating than Stock A ({score_a:.2f})"
        )
        
        # Verify that Stock B's overall Total Value Score is also higher
        total_a = result_df.loc[result_df["Ticker"] == "STOCK_A", "Total Value Score"].iloc[0]
        total_b = result_df.loc[result_df["Ticker"] == "STOCK_B", "Total Value Score"].iloc[0]
        self.assertGreater(
            total_b, total_a,
            "Expected Stock B to have a better Total Value Score than Stock A"
        )

if __name__ == '__main__':
    unittest.main()
