import pandas as pd
import numpy as np

def apply_weighted_scoring(df):
    """
    Applies a weighted percentile ranking system to the stock data, 
    tailored for long-term growth and compounding returns.
    """
    print("Calculating weighted Total and Industry percentile scores...")

    # 1. Force all scraped metrics to be recognized as numbers
    metrics_to_keep = [
        "P/E", "EPS", "Osinko/osake", "Osinkotuotto", 
        "P/B", "PEG", "P/S", "Liikevaihto", "EBIT", 
        "Omistajia Nordnetissä*", "Analyst Rating",
        "Worst Case", "Probable Case", "Best Case" # Added the manual columns here
    ]
    for col in metrics_to_keep:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # --- NEW: CALCULATE THE RISK METRICS ---
    # Check if the manual risk columns exist before doing the math
    if "Worst Case" in df.columns and "Probable Case" in df.columns and "Best Case" in df.columns:
        # PERT Formula: (Worst + 4*Probable + Best) / 6
        df["Expected Upside"] = (df["Worst Case"] + (4 * df["Probable Case"]) + df["Best Case"]) / 6
    else:
        # If the user hasn't added the columns to Excel yet, create empty ones so the script doesn't crash
        df["Expected Upside"] = np.nan
        df["Worst Case"] = np.nan

    # =========================================================
    # 2. METRIC THEORY, TARGETS, AND MULTIPLIER WEIGHTS
    # =========================================================

    target_metrics = {
        "P/E": {"target": 15.0, "weight": 0.10}  # Adjusted to 10%
    }

    # Inside scoring_engine.py
    higher_metrics = {
        "EPS": 0.30,          # Increased to 30% (The most important growth factor)
        "EBIT": 0.15,         # Increased to 15% (Proves the business model works)
        "Liikevaihto": 0.05,  # Lowered to 5%
        "Osinkotuotto": 0.0,  # Zeroed out (Ignored)
        "Analyst Rating": 0.05,  
        "Omistajia Nordnetissä*": 0.05,  
        "Expected Upside": 0.10, 
        "Worst Case": 0.05 
    }

    lower_metrics = {
        "PEG": 0.10,  # Adjusted to 10%
        "P/B": 0.05   # 5%
    }

    # =========================================================
    # 3. THE MATHEMATICAL ENGINE
    # =========================================================
    
    total_points = pd.Series(0.0, index=df.index)
    total_weights = pd.Series(0.0, index=df.index)
    ind_points = pd.Series(0.0, index=df.index)
    ind_weights = pd.Series(0.0, index=df.index)

    def process_metric(rank_series, ind_rank_series, weight):
        valid_mask = rank_series.notna()
        total_points[valid_mask] += rank_series[valid_mask] * weight
        total_weights[valid_mask] += weight
        ind_points[valid_mask] += ind_rank_series[valid_mask] * weight
        ind_weights[valid_mask] += weight

    for metric, config in target_metrics.items():
        if metric in df.columns:
            dist = (df[metric] - config["target"]).abs()
            t_rank = dist.rank(ascending=False, pct=True)
            i_rank = df.groupby('Industry')[metric].apply(
                lambda x: (x - config["target"]).abs().rank(ascending=False, pct=True)
            ).reset_index(level=0, drop=True)
            process_metric(t_rank, i_rank, config["weight"])

    for metric, weight in higher_metrics.items():
        if metric in df.columns:
            t_rank = df[metric].rank(ascending=True, pct=True)
            i_rank = df.groupby('Industry')[metric].rank(ascending=True, pct=True)
            process_metric(t_rank, i_rank, weight)

    for metric, weight in lower_metrics.items():
        if metric in df.columns:
            t_rank = df[metric].rank(ascending=False, pct=True)
            i_rank = df.groupby('Industry')[metric].rank(ascending=False, pct=True)
            process_metric(t_rank, i_rank, weight)

    # =========================================================
    # 4. FINAL CALCULATION
    # =========================================================
    
    df["Total Value Score"] = np.where(total_weights > 0, (total_points / total_weights) * 100, np.nan)
    df["Industry Value Score"] = np.where(ind_weights > 0, (ind_points / ind_weights) * 100, np.nan)
    
    df["Total Value Score"] = df["Total Value Score"].round(2)
    df["Industry Value Score"] = df["Industry Value Score"].round(2)

    return df