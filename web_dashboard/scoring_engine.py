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
        
        # 1. Calculate Expected Upside using PERT (Inputs are already percentages)
        df["Expected Upside"] = (df["Worst Case"] + (4 * df["Probable Case"]) + df["Best Case"]) / 6
        
        # SAFETY NET: If PERT fails because Worst/Best are blank, but Probable exists, use Probable.
        df["Expected Upside"] = df["Expected Upside"].fillna(df["Probable Case"])
        
        # 2. Calculate the Spread (Volatility Percentage)
        # Since the inputs are already percentages, the spread is just the absolute difference!
        df["Risk Spread"] = (df["Best Case"] - df["Worst Case"]).abs()
        
    else:
        df["Expected Upside"] = np.nan
        df["Worst Case"] = np.nan
        df["Risk Spread"] = np.nan

    # =========================================================
    # 2. METRIC THEORY, TARGETS, AND MULTIPLIER WEIGHTS
    # =========================================================
    # Total weights below equal 1.0 (100%) for a pure Fundamental Value Score.
    #
    # WEIGHT RATIONALE:
    # P/E is reduced from 0.30 → 0.15 because PEG already contains P/E in its
    # numerator (PEG = P/E ÷ EPS growth rate). Giving both equal high weight
    # caused earnings valuation to dominate ~60% of the score redundantly.
    # The freed weight is redistributed to Analyst Rating (professional consensus),
    # EBIT (operating profitability — are they actually making money?), and
    # EPS (earnings per share — core long-term compounder signal).
    # P/B is trimmed slightly because it is less meaningful for asset-light
    # tech and pharma firms common on OMXH.

    target_metrics = {
        # Valuation Anchor: Reward stocks trading close to a fair 15x P/E.
        # Reduced from 0.30 to avoid double-counting with PEG.
        "P/E": {"target": 15.0, "weight": 0.15}
    }

    higher_metrics = {
        # Sentiment: Professional analyst consensus (1 to 5 scale).
        # Raised from 0.10 — analyst consensus is a meaningful signal.
        "Analyst Rating": 0.15,

        # Profitability: Higher EBIT = company actually generates operating profit.
        # Activated from 0.0 — critical signal that was previously ignored.
        "EBIT": 0.10,

        # Growth: Higher EPS rewards profitable compounders.
        # Activated from 0.0 — key long-term signal.
        "EPS": 0.10,

        # Unweighted tracking metrics (kept at 0.0 to prevent engine crashes,
        # but completely excluded from the actual mathematical ranking).
        "Osinkotuotto": 0.0,
        "Omistajia Nordnetissä*": 0.0,
        "Liikevaihto": 0.0
    }

    lower_metrics = {
        # Growth Anchor: PEG is the most complete valuation metric as it
        # normalises P/E by earnings growth. Primary driver of the score.
        "PEG": 0.25,

        # Asset Valuation: Price to Book value.
        # Trimmed from 0.15 — less relevant for asset-light OMXH sectors.
        "P/B": 0.10,

        # Revenue Valuation: Price to Sales — universally applicable.
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