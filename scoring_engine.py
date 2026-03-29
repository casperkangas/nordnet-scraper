import pandas as pd
import numpy as np

def apply_weighted_scoring(df):
    """
    Applies a weighted percentile ranking system to the stock data, 
    tailored for long-term growth and compounding returns.
    """
    print("Calculating weighted Total and Industry percentile scores...")

    metrics_to_keep = [
        "P/E", "EPS", "Osinko/osake", "Osinkotuotto", 
        "P/B", "PEG", "P/S", "Liikevaihto", "EBIT", 
        "Omistajia Nordnetissä*", "Analyst Rating",
        "Worst Case", "Probable Case", "Best Case"
    ]
    for col in metrics_to_keep:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # =========================================================
    # 1. NEW: CALCULATE THE RISK METRICS & SPREAD
    # =========================================================
    if "Worst Case" in df.columns and "Probable Case" in df.columns and "Best Case" in df.columns:
        
        # Calculate Expected Upside using PERT
        df["Expected Upside"] = (df["Worst Case"] + (4 * df["Probable Case"]) + df["Best Case"]) / 6
        
        # SAFETY NET: If PERT fails because Worst/Best are blank, but Probable exists, use Probable.
        df["Expected Upside"] = df["Expected Upside"].fillna(df["Probable Case"])
        
        # Calculate the Spread (Volatility). Higher spread = more risk.
        df["Risk Spread"] = df["Best Case"] - df["Worst Case"]
        
    else:
        df["Expected Upside"] = np.nan
        df["Worst Case"] = np.nan
        df["Risk Spread"] = np.nan

    # =========================================================
    # 2. METRIC THEORY, TARGETS, AND MULTIPLIER WEIGHTS
    # =========================================================

    target_metrics = {
        "P/E": {"target": 15.0, "weight": 0.10}  # 10%
    }

    higher_metrics = {
        "EPS": 0.30,          # 30% 
        "EBIT": 0.15,         # 15% 
        "Liikevaihto": 0.0,   # Removed weight, replaced by our specific risk cases
        
        "Expected Upside": 0.10, # 10% 
        "Worst Case": 0.05,      # 5% 
        
        "Analyst Rating": 0.05,   # 5%
        "Osinkotuotto": 0.0, 
        "Omistajia Nordnetissä*": 0.0 
    }

    lower_metrics = {
        "PEG": 0.15,  # 15% 
        "P/B": 0.05,  # 5%
        
        # --- NEW SPREAD METRIC ---
        # Ranked lower-is-better because a smaller spread means higher analyst certainty.
        "Risk Spread": 0.05 # 5%
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