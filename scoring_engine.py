import pandas as pd
import numpy as np

def apply_weighted_scoring(df):
    """
    Applies a weighted percentile ranking system to the stock data, 
    tailored for long-term growth and compounding returns.
    """
    print("Calculating weighted Total and Industry percentile scores...")

    # 1. Force all metrics to be recognized as numbers
    metrics_to_keep = [
        "P/E", "EPS", "Osinko/osake", "Osinkotuotto", 
        "P/B", "PEG", "P/S", "Liikevaihto", "EBIT", 
        "Omistajia Nordnetissä*", "Analyst Rating"
    ]
    for col in metrics_to_keep:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # =========================================================
    # 2. METRIC THEORY, TARGETS, AND MULTIPLIER WEIGHTS
    # =========================================================

    # --- THE SWEET SPOT (Distance-based) ---
    # P/E: Price-to-Earnings. How much you pay for €1 of profit.
    # Long-Term Theory: A low P/E is good, but a P/E under 10 often signals a "value trap" 
    # (the market expects profits to collapse). We target a healthy 15.0.
    target_metrics = {
        "P/E": {"target": 15.0, "weight": 0.15}  # 15% of total score
    }

    # --- THE GROWTH & COMPOUNDING ENGINE (Higher is Better) ---
    higher_metrics = {
        # EPS (Earnings Per Share): The #1 driver of stock prices. 
        # Ideal Target: Consistent positive growth year-over-year.
        "EPS": 0.20,  # 20% - Heaviest weight for long-term growth
        
        # Liikevaihto (Revenue): Total money coming in. 
        # Ideal Target: Steady growth. Proves the business is actually expanding.
        "Liikevaihto": 0.15,  # 15%
        
        # EBIT (Operating Profit): Profit before taxes. 
        # Ideal Target: Positive margins. Proves the core product makes money.
        "EBIT": 0.10,  # 10%
        
        # Osinkotuotto (Dividend Yield): Getting paid to wait. 
        # Ideal Target: 3% to 5%. Reinvesting this creates compound interest.
        "Osinkotuotto": 0.10,  # 10%
        
        # Analyst Rating: Professional market sentiment. 
        # Ideal Target: > 3.5 on a 1-to-5 scale.
        "Analyst Rating": 0.05,  # 5%
        
        # Omistajia Nordnetissä*: Retail investor sentiment. 
        # Ideal Target: Growing owner base over time.
        "Omistajia Nordnetissä*": 0.05  # 5%
    }

    # --- THE VALUATION PROTECTORS (Lower is Better) ---
    lower_metrics = {
        # PEG (Price/Earnings-to-Growth): The holy grail connector. 
        # Ideal Target: < 1.0. This means the stock is cheap relative to its expected future growth.
        "PEG": 0.15,  # 15%
        
        # P/B (Price-to-Book): What you pay vs the company's liquidation value. 
        # Ideal Target: < 3.0 (Under 1.0 is a deep discount, great for banks/industrials).
        "P/B": 0.05   # 5%
    }
    
    # Note: P/S (Price-to-Sales) is currently unweighted (0%) to keep the total at 100%, 
    # but the data is preserved in the file for your manual review.

    # =========================================================
    # 3. THE MATHEMATICAL ENGINE (Handling missing data fairly)
    # =========================================================
    
    # Create empty trackers to tally up the points and weights for each stock
    total_points = pd.Series(0.0, index=df.index)
    total_weights = pd.Series(0.0, index=df.index)
    ind_points = pd.Series(0.0, index=df.index)
    ind_weights = pd.Series(0.0, index=df.index)

    # Helper function to assign points only if the data exists
    def process_metric(rank_series, ind_rank_series, weight):
        valid_mask = rank_series.notna()
        total_points[valid_mask] += rank_series[valid_mask] * weight
        total_weights[valid_mask] += weight
        ind_points[valid_mask] += ind_rank_series[valid_mask] * weight
        ind_weights[valid_mask] += weight

    # Calculate Sweet Spot Ranks
    for metric, config in target_metrics.items():
        if metric in df.columns:
            dist = (df[metric] - config["target"]).abs()
            t_rank = dist.rank(ascending=False, pct=True)
            i_rank = df.groupby('Industry')[metric].apply(
                lambda x: (x - config["target"]).abs().rank(ascending=False, pct=True)
            ).reset_index(level=0, drop=True)
            process_metric(t_rank, i_rank, config["weight"])

    # Calculate Higher-is-Better Ranks
    for metric, weight in higher_metrics.items():
        if metric in df.columns:
            t_rank = df[metric].rank(ascending=True, pct=True)
            i_rank = df.groupby('Industry')[metric].rank(ascending=True, pct=True)
            process_metric(t_rank, i_rank, weight)

    # Calculate Lower-is-Better Ranks
    for metric, weight in lower_metrics.items():
        if metric in df.columns:
            t_rank = df[metric].rank(ascending=False, pct=True)
            i_rank = df.groupby('Industry')[metric].rank(ascending=False, pct=True)
            process_metric(t_rank, i_rank, weight)

    # =========================================================
    # 4. FINAL CALCULATION
    # =========================================================
    
    # Divide the earned points by the total possible weights available to that specific stock.
    # This prevents stocks with missing data from being mathematically punished.
    df["Total Value Score"] = np.where(total_weights > 0, (total_points / total_weights) * 100, np.nan)
    df["Industry Value Score"] = np.where(ind_weights > 0, (ind_points / ind_weights) * 100, np.nan)
    
    df["Total Value Score"] = df["Total Value Score"].round(2)
    df["Industry Value Score"] = df["Industry Value Score"].round(2)

    return df