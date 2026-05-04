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
        
        # Calculate the Spread (Volatility Percentage)
        # 1. Use .abs() to prevent negative risk if an analyst enters Worst > Best
        # 2. Divide by Probable Case to normalize the risk regardless of share price
        spread_currency = (df["Best Case"] - df["Worst Case"]).abs()
        df["Risk Spread"] = (spread_currency / df["Probable Case"].replace(0, np.nan)) * 100
        
    else:
        df["Expected Upside"] = np.nan
        df["Worst Case"] = np.nan
        df["Risk Spread"] = np.nan

    # =========================================================
    # 2. METRIC THEORY, TARGETS, AND MULTIPLIER WEIGHTS
    # =========================================================
    # Total weights below equal 1.0 (100%) for a pure Fundamental Value Score.

    target_metrics = {
        # Valuation Anchor: Target a healthy 15.0 P/E
        "P/E": {"target": 15.0, "weight": 0.30}  
    }

    higher_metrics = {
        # Sentiment: Professional analyst consensus (1 to 5 scale)
        "Analyst Rating": 0.10,   
        
        # Unweighted tracking metrics (Kept at 0.0 to prevent engine crashes, 
        # but completely ignored in the actual mathematical ranking)
        "Osinkotuotto": 0.0, 
        "Omistajia Nordnetissä*": 0.0,
        "Liikevaihto": 0.0
    }

    lower_metrics = {
        # Growth Anchor: Price to Earnings Growth (balances the P/E)
        "PEG": 0.30,  
        
        # Asset Valuation: Price to Book value
        "P/B": 0.15,  
        
        # Revenue Valuation: Price to Sales (safely replaces raw Liikevaihto)
        "P/S": 0.15   
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
    # 4. FINAL CALCULATION & DATA COVERAGE PENALTY
    # =========================================================
    
    # 1. Calculate the raw base score (ignoring missing data)
    raw_total_score = np.where(total_weights > 0, (total_points / total_weights) * 100, np.nan)
    raw_ind_score = np.where(ind_weights > 0, (ind_points / ind_weights) * 100, np.nan)
    
    # 2. Calculate the "Data Completeness" ratio dynamically
    # We safely sum up all the weights you defined in your dictionaries above
    max_target_weight = sum(config["weight"] for config in target_metrics.values())
    max_higher_weight = sum(higher_metrics.values())
    max_lower_weight = sum(lower_metrics.values())
    
    max_possible_weight = max_target_weight + max_higher_weight + max_lower_weight
    
    # Ratio will be exactly between 0.0 and 1.0
    coverage_ratio = total_weights / max_possible_weight
    
    # 3. Apply the penalty multiplier
    df["Total Value Score"] = (raw_total_score * coverage_ratio).round(2)
    df["Industry Value Score"] = (raw_ind_score * coverage_ratio).round(2)
    
    # 4. Add a transparency column so you can see exactly how much data a stock had
    df["Data Completeness %"] = (coverage_ratio * 100).round(0)

    return df