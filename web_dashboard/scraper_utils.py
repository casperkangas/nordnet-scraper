import pandas as pd
import numpy as np

def build_rankings_by_date(df):
    rankings = {}

    for run_date in sorted(df['Date'].dropna().unique()):
        day_df = df[df['Date'] == run_date].copy()
        day_df = day_df.sort_values(by='⭐ Composite Score', ascending=False).reset_index(drop=True)
        day_df['Rank'] = day_df.index + 1
        rankings[run_date] = dict(zip(day_df['Ticker'], day_df['Rank']))

    return rankings

def _normalize_series(s, invert=False, clip_pct=(5, 95)):
    clean_s = s.dropna()
    if clean_s.empty:
        return pd.Series(np.nan, index=s.index)
    lo = np.nanpercentile(clean_s, clip_pct[0])
    hi = np.nanpercentile(clean_s, clip_pct[1])
    if hi == lo:
        return pd.Series(50.0, index=s.index)
    clipped = s.clip(lower=lo, upper=hi)
    scaled  = (clipped - lo) / (hi - lo) * 100
    return (100 - scaled) if invert else scaled

def _calc_composite_for_group(group):
    W_TOTAL    = 0.35
    W_INDUSTRY = 0.20
    W_UPSIDE   = 0.30
    W_RISK     = 0.15

    score_parts = []
    weight_parts = []

    if 'Total Value Score' in group.columns:
        norm = _normalize_series(group['Total Value Score'])
        score_parts.append(norm * W_TOTAL)
        weight_parts.append(norm.notna().astype(float) * W_TOTAL)
    if 'Industry Value Score' in group.columns:
        norm = _normalize_series(group['Industry Value Score'])
        score_parts.append(norm * W_INDUSTRY)
        weight_parts.append(norm.notna().astype(float) * W_INDUSTRY)
    if 'Expected Upside' in group.columns:
        norm = _normalize_series(group['Expected Upside'])
        score_parts.append(norm * W_UPSIDE)
        weight_parts.append(norm.notna().astype(float) * W_UPSIDE)
    if 'Risk Spread' in group.columns:
        norm = _normalize_series(group['Risk Spread'], invert=True)
        score_parts.append(norm * W_RISK)
        weight_parts.append(norm.notna().astype(float) * W_RISK)
    
    if score_parts:
        raw_sum = pd.concat(score_parts, axis=1).sum(axis=1)
        total_weight = pd.concat(weight_parts, axis=1).sum(axis=1)
        return (raw_sum / total_weight.replace(0, np.nan)).round(1)
    else:
        return pd.Series(np.nan, index=group.index)

def format_rank_change(current_rank, previous_rank):
    if pd.isna(previous_rank):
        return '-'
    delta = int(previous_rank) - int(current_rank)
    if delta > 0:
        return f'↑ {delta}'
    if delta < 0:
        return f'↓ {abs(delta)}'
    return '-'
