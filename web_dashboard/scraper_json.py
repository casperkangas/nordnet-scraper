from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import date, datetime, timedelta
import os
import numpy as np
import glob
from scoring_engine import apply_weighted_scoring
import time
import matplotlib.pyplot as plt

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

# --- NEW: START THE TIMER ---
print("⏱️ Starting the scraping engine...")
start_time = time.time()

# 1. Create the Master List to hold all stocks
all_stocks_data = []

# 2. Define the strict allowlist
metrics_to_keep = [
    "P/E", "EPS", "Osinko/osake", "Osinkotuotto", 
    "P/B", "PEG", "P/S", "Liikevaihto", "EBIT", 
    "Omistajia Nordnetissä*"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def build_rankings_by_date(df):
    rankings = {}

    for run_date in sorted(df['Date'].dropna().unique()):
        day_df = df[df['Date'] == run_date].copy()
        day_df = day_df.sort_values(by='⭐ Composite Score', ascending=False).reset_index(drop=True)
        day_df['Rank'] = day_df.index + 1
        rankings[run_date] = dict(zip(day_df['Ticker'], day_df['Rank']))

    return rankings

# 3. Use glob to find all text files that start with "targets_"
target_files = sorted(glob.glob(os.path.join(project_root, "targets_*.txt")))

if not target_files:
    print("No target files found! Make sure they are named like 'targets_finance.txt'")

# --- 3. LAUNCH PLAYWRIGHT BROWSER ---
print("Starting Playwright Headless Browser...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) # Set to False to see the browser in action, True for headless mode
    
    # Create a context that looks like a real Mac computer
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    
    # --- NEW: SPEED OPTIMIZATION (RESOURCE BLOCKING) ---
    # Intercept all network requests. If it is an image, CSS, or font, block it.
    page.route("**/*", lambda route: route.abort() 
               if route.request.resource_type in ["image", "stylesheet", "font"] 
               else route.continue_())
    # ---------------------------------------------------

    # 4. The Outer Loop: Go through every text file found
    for file_path in target_files:
        
        filename = os.path.basename(file_path)
        industry_name = filename.replace("targets_", "").replace(".txt", "").replace("_", " ").title()
        
        print(f"\n--- Processing Industry: {industry_name} ---")
        
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()

        # 5. The Inner Loop: Go through each line in the text file
        for line in lines:
            clean_line = line.strip()
            
            if not clean_line:
                continue 
                
            parts = clean_line.split(",")
            ticker = parts[0].strip()
            url = parts[1].strip()
            
            print(f"Scraping data for: {ticker}...")
            
            try:
                # 1. Instruct the browser to go to the URL (Wait until DOM is loaded, generous 30s timeout)
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # 2. DYNAMIC WAIT: Wait dynamically for price & metric elements to render.
                # Playwright proceeds IMMEDIATELY once painted, avoiding wasted time locally
                # while giving GitHub Actions runners up to 30s during network/CPU spikes.
                price_locator = page.locator("span[class*='typography-title2'][class*='font-extrabold']")
                try:
                    price_locator.first.wait_for(state="attached", timeout=30000)
                except Exception as e:
                    print(f"  -> Notice: Price locator wait timed out for {ticker}. Error: {e}")

                try:
                    page.locator("button[aria-label*=':']").first.wait_for(state="attached", timeout=30000)
                except Exception as e:
                    print(f"  -> Notice: Financial metric locator wait timed out for {ticker}. Error: {e}")

                # 3. Grab ALL buttons immediately once metrics are painted
                buttons = page.query_selector_all('button')
                
                stock_data = {}
                stock_data["Ticker"] = ticker
                stock_data["Date"] = str(date.today())
                stock_data["Industry"] = industry_name
                
                # ==========================================
                # --- NEW: GRAB THE CURRENT PRICE ---
                # ==========================================
                stock_data["Current Price"] = None  
                
                try:
                    element_count = price_locator.count()
                    
                    for i in range(element_count):
                        # Bypass CSS visibility rules
                        raw_price = price_locator.nth(i).text_content()
                        
                        if raw_price:
                            clean_price = raw_price.replace(" ", "").replace("\xa0", "").replace(",", ".")
                            
                            try:
                                stock_data["Current Price"] = float(clean_price)
                                break  # We found the real price, stop looking!
                            except ValueError:
                                pass
                                
                except Exception as e:
                    print(f"  -> Notice: Could not locate price for {ticker}. Error: {e}")
                # ==========================================
                                
                for button in buttons:
                    # Playwright uses get_attribute instead of get
                    aria_label = button.get_attribute('aria-label')
                    
                    if aria_label and ":" in aria_label:
                        label_parts = aria_label.split(":")
                        metric_name = label_parts[0].strip()
                        
                        if metric_name in metrics_to_keep:
                            raw_value = label_parts[1].strip()
                            
                            if "Ei käytettävissä" in raw_value:
                                clean_value = None 
                            else:
                                clean_text = raw_value.replace("EUR", "").replace("%", "").strip()
                                try:
                                    clean_value = float(clean_text)
                                except ValueError:
                                    clean_value = clean_text 
                            
                            stock_data[metric_name] = clean_value
                
                all_stocks_data.append(stock_data)
                
            except Exception as e:
                print(f"Failed to retrieve {ticker}. Error: {e}")

    # Close the browser safely when all files are finished
    print("Closing browser...")
    browser.close()
    
# --- EXCEL EXPORT & MERGE LOGIC ---

print("\nConverting data to a table...")
df = pd.DataFrame(all_stocks_data)

# --- THE FIX: Anchor the paths securely to the script's exact location ---
data_dir = os.path.join(script_dir, "data")

# 3. Create it if it doesn't exist
os.makedirs(data_dir, exist_ok=True)

# 4. Route the master database securely into the anchored folder
output_filename = os.path.join(data_dir, "Stock_Analysis_Master.json")

# 6. INTEGRATE MANUAL ANALYST RATINGS
manual_file = os.path.join(project_root, "Manual_Analyst_Ratings.xlsx")

if os.path.exists(manual_file):
    print(f"Found {manual_file}. Merging analyst scores...")
    manual_df = pd.read_excel(manual_file)
    df = pd.merge(df, manual_df, on="Ticker", how="left")
    
    # Calculate the 1-to-5 Analyst Rating scale
    df["Total Analysts"] = df["Buy"] + df["Hold"] + df["Sell"]
    df["Total Points"] = (df["Buy"] * 5) + (df["Hold"] * 3) + (df["Sell"] * 1)
    
    df["Analyst Rating"] = np.where(
        df["Total Analysts"] > 0, 
        df["Total Points"] / df["Total Analysts"], 
        None
    )
    df = df.drop(columns=["Total Points"])
else:
    print(f"Notice: {manual_file} not found. Skipping analyst scores.")
    
df = apply_weighted_scoring(df)

# =========================================================
# 8. HISTORY APPENDING & DASHBOARD SEPARATION
# =========================================================

if os.path.exists(output_filename):
    print(f"Found existing {output_filename}. Appending new data...")
    historical_df = pd.read_json(output_filename)
    final_df = pd.concat([historical_df, df], ignore_index=True)
else:
    print(f"No existing file found. Creating a fresh {output_filename}...")
    final_df = df

# 1. First, strip out all Timestamps and force every date strictly to Text
final_df['Date'] = pd.to_datetime(final_df['Date']).dt.strftime('%Y-%m-%d')

# 2. Second, drop the duplicates so only the absolute latest run per day survives
final_df = final_df.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
# ------------------------------------

# --- Calculate Composite Score for the entire history ---
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
    if 'Total Value Score' in group.columns:
        score_parts.append(_normalize_series(group['Total Value Score']) * W_TOTAL)
    if 'Industry Value Score' in group.columns:
        score_parts.append(_normalize_series(group['Industry Value Score']) * W_INDUSTRY)
    if 'Expected Upside' in group.columns:
        score_parts.append(_normalize_series(group['Expected Upside']) * W_UPSIDE)
    if 'Risk Spread' in group.columns:
        score_parts.append(_normalize_series(group['Risk Spread'], invert=True) * W_RISK)
    
    if score_parts:
        return pd.concat(score_parts, axis=1).sum(axis=1).round(1)
    else:
        return pd.Series(np.nan, index=group.index)

final_df['⭐ Composite Score'] = final_df.groupby('Date', group_keys=False).apply(_calc_composite_for_group)

# Separate ONLY today's data for the Snapshot dashboard
today_str = str(date.today())
today_df = final_df[final_df['Date'] == today_str].copy()
today_df = today_df.sort_values(by="⭐ Composite Score", ascending=False)

# Identify the historical dates for our comparisons
past_dates = sorted(final_df[final_df['Date'] < today_str]['Date'].unique())
last_date = past_dates[-1] if past_dates else None
rankings_by_date = build_rankings_by_date(final_df)
previous_ranks = rankings_by_date.get(last_date, {}) if last_date else {}

# =========================================================
# --- GENERATE THE SCORE TREND MATRIX ---
# =========================================================
print("Generating the historical score matrix...")

trend_df = final_df.pivot(index='Ticker', columns='Date', values='⭐ Composite Score').reset_index()

if today_str in trend_df.columns:
    trend_df = trend_df.rename(columns={today_str: 'Current Score'})
else:
    trend_df['Current Score'] = np.nan

recent_past_dates = past_dates[-9:]

# Interleave the columns: Ticker -> Current -> Date 1 -> Date 1 % -> Date 2 -> Date 2 %
score_cols = ['Ticker', 'Current Score']
for d in recent_past_dates:
    if d in trend_df.columns:
        diff_col = f"{d} Diff %"
        # Calculate the percentage difference and restrict to 2 decimals
        trend_df[diff_col] = (((trend_df['Current Score'] - trend_df[d]) / trend_df[d].replace(0, np.nan)) * 100).round(2)
        score_cols.extend([d, diff_col])

# Filter and sort
existing_score_cols = [c for c in score_cols if c in trend_df.columns]
trend_df = trend_df[existing_score_cols]
trend_df = trend_df.sort_values(by='Current Score', ascending=False)

# =========================================================
# --- GENERATE THE PRICE TREND MATRIX ---
# =========================================================
print("Generating the historical price matrix...")

if 'Current Price' in final_df.columns:
    price_trend_df = final_df.pivot(index='Ticker', columns='Date', values='Current Price').reset_index()
    
    if today_str in price_trend_df.columns:
        price_trend_df = price_trend_df.rename(columns={today_str: 'Current Price'})
    else:
        price_trend_df['Current Price'] = np.nan
        
    price_cols = ['Ticker', 'Current Price']
    for d in recent_past_dates:
        if d in price_trend_df.columns:
            diff_col = f"{d} Diff %"
            # Calculate the percentage difference and restrict to 2 decimals
            price_trend_df[diff_col] = (((price_trend_df['Current Price'] - price_trend_df[d]) / price_trend_df[d].replace(0, np.nan)) * 100).round(2)
            price_cols.extend([d, diff_col])
            
    existing_price_cols = [c for c in price_cols if c in price_trend_df.columns]
    price_trend_df = price_trend_df[existing_price_cols]
    
    # --- NEW: Sort by the most recent % difference (Momentum) ---
    if recent_past_dates:
        latest_diff_col = f"{recent_past_dates[-1]} Diff %"
        if latest_diff_col in price_trend_df.columns:
            price_trend_df = price_trend_df.sort_values(by=latest_diff_col, ascending=False)
        else:
            price_trend_df = price_trend_df.sort_values(by='Current Price', ascending=False)
    else:
        price_trend_df = price_trend_df.sort_values(by='Current Price', ascending=False)

# =========================================================
# --- MOMENTUM COUNTS: period-over-period consecutive diffs ---
# =========================================================
# IMPORTANT: We do NOT use the Diff% display columns here because those
# compare every historical date back to TODAY, meaning a stock that peaked
# 6 months ago and has since declined would show mostly "negative" counts
# even if it was rising for 5 of those 6 months.
# Instead, we pivot the raw data and compute date[i] vs date[i-1] diffs,
# which correctly captures directional movement between each consecutive scrape.
print("Calculating momentum counts (period-over-period consecutive changes)...")

# --- Price momentum (period-over-period) ---
if 'Current Price' in final_df.columns:
    _price_pivot = final_df.pivot_table(
        index='Ticker', columns='Date', values='Current Price', aggfunc='last'
    )
    _price_sorted = _price_pivot[sorted(_price_pivot.columns)]
    # diff(axis=1) gives col[i] - col[i-1]; first column becomes NaN (correct)
    _price_consec = _price_sorted.diff(axis=1).iloc[:, 1:]
    price_pos = (_price_consec > 0).sum(axis=1).rename("Price ↑")
    price_neg = (_price_consec < 0).sum(axis=1).rename("Price ↓")
    momentum_price = pd.concat([price_pos, price_neg], axis=1).reset_index()
    today_df = today_df.merge(momentum_price, on='Ticker', how='left')

# --- Score momentum (period-over-period) ---
_score_pivot = final_df.pivot_table(
    index='Ticker', columns='Date', values='⭐ Composite Score', aggfunc='last'
)
_score_sorted = _score_pivot[sorted(_score_pivot.columns)]
_score_consec = _score_sorted.diff(axis=1).iloc[:, 1:]
score_pos = (_score_consec > 0).sum(axis=1).rename("Score ↑")
score_neg = (_score_consec < 0).sum(axis=1).rename("Score ↓")
momentum_score = pd.concat([score_pos, score_neg], axis=1).reset_index()
today_df = today_df.merge(momentum_score, on='Ticker', how='left')

# =========================================================
# --- COMPOSITE & MOMENTUM SCORES ---
# =========================================================
print("Computing composite and momentum scores...")


# --- Momentum Score: how consistently the stock trends upward ---
momentum_parts = []
total_price_obs = None
total_score_obs = None

if 'Price ↑' in today_df.columns and 'Price ↓' in today_df.columns:
    total_price_obs = today_df['Price ↑'] + today_df['Price ↓']
    price_ratio = (today_df['Price ↑'] / total_price_obs.replace(0, np.nan)) * 100
    momentum_parts.append(price_ratio * 0.50)

if 'Score ↑' in today_df.columns and 'Score ↓' in today_df.columns:
    total_score_obs = today_df['Score ↑'] + today_df['Score ↓']
    score_ratio = (today_df['Score ↑'] / total_score_obs.replace(0, np.nan)) * 100
    momentum_parts.append(score_ratio * 0.50)

if momentum_parts:
    today_df['📈 Momentum Score'] = pd.concat(momentum_parts, axis=1).sum(axis=1).round(1)

# Re-sort the snapshot by the new master score
if '⭐ Composite Score' in today_df.columns:
    today_df = today_df.sort_values(by='⭐ Composite Score', ascending=False)
    
today_df = today_df.reset_index(drop=True)
today_df['Current Rank'] = today_df.index + 1
today_df['Previous Rank'] = today_df['Ticker'].map(previous_ranks)

def format_rank_change(current_rank, previous_rank):
    if pd.isna(previous_rank):
        return '-'
    delta = int(previous_rank) - int(current_rank)
    if delta > 0:
        return f'↑ {delta}'
    if delta < 0:
        return f'↓ {abs(delta)}'
    return '-'

today_df['Rank Change'] = today_df.apply(
    lambda row: format_rank_change(row['Current Rank'], row['Previous Rank']),
    axis=1
)

today_df['Rank Change Value'] = today_df.apply(
    lambda row: 0 if pd.isna(row['Previous Rank']) else int(row['Previous Rank']) - int(row['Current Rank']),
    axis=1
)

target_date_7d = str(datetime.strptime(today_str, "%Y-%m-%d").date() - timedelta(days=7))
valid_7d_dates = [d for d in past_dates if d <= target_date_7d]
date_7d = valid_7d_dates[-1] if valid_7d_dates else None
previous_7d_ranks = rankings_by_date.get(date_7d, {}) if date_7d else {}

today_df['Previous Rank 7d'] = today_df['Ticker'].map(previous_7d_ranks)

today_df['7-Day Rank Change'] = today_df.apply(
    lambda row: format_rank_change(row['Current Rank'], row['Previous Rank 7d']),
    axis=1
)

today_df['7-Day Rank Change Value'] = today_df.apply(
    lambda row: 0 if pd.isna(row['Previous Rank 7d']) else int(row['Previous Rank 7d']) - int(row['Current Rank']),
    axis=1
)

today_df = today_df.drop(columns=['Previous Rank 7d'], errors='ignore')


# =========================================================
# --- NEW: GENERATE RISK VS REWARD SCATTER PLOT ---
# =========================================================
print("Generating Risk vs. Reward visualization...")

# 1. Isolate the data: Drop any stocks missing these metrics so the math doesn't crash
plot_df = today_df.dropna(subset=['Risk Spread', 'Expected Upside']).copy()

# 2. Define our axes
x = plot_df['Risk Spread']       # X-axis: Risk (Volatility / Uncertainty)
y = plot_df['Expected Upside']   # Y-axis: Reward (Potential Growth)
tickers = plot_df['Ticker']      # Labels: The company names

# 3. Create the blank canvas (10 inches wide by 6 inches tall)
plt.figure(figsize=(10, 6))

# 4. Draw the dots
plt.scatter(x, y, color='#2196F3', alpha=0.7, edgecolors='black', s=50)

# 5. Attach the Ticker names slightly offset from each dot
for i, ticker in enumerate(tickers):
    plt.annotate(ticker, (x.iloc[i], y.iloc[i]), xytext=(5, 5), textcoords='offset points', fontsize=8)

# 6. Add titles and gridlines to make it highly readable
plt.title(f'Risk vs. Reward Matrix ({today_str})', fontsize=14, fontweight='bold')
plt.xlabel('Risk Spread (Best Case minus Worst Case)', fontsize=12)
plt.ylabel('Expected Upside %', fontsize=12)
plt.grid(True, linestyle='--', alpha=0.5)

# 7. Add a "Zero Line" to instantly see negative upside stocks
plt.axhline(0, color='red', linestyle='-', linewidth=1.5, alpha=0.8)

# 8. Save the chart as a static image file securely into the anchored folder
plot_filename = os.path.join(data_dir, "Risk_Reward_Latest.png")
plt.savefig(plot_filename, bbox_inches='tight', dpi=150)
plt.close() # Free up computer memory

print(f"Saved visualization as {plot_filename}")

# =========================================================
# 9. EXPORT DATA PANELS TO JSON FOR WEB DASHBOARD
# =========================================================
print("Saving database and exporting web-ready JSON panels...")

# 1. Update the master history ledger database
final_df.to_json(output_filename, orient="records", force_ascii=False, indent=4)

# 2. Export the static UI panels into the anchored data directory
today_df.to_json(os.path.join(data_dir, "web_today_snapshot.json"), orient="records", force_ascii=False, indent=4)
trend_df.to_json(os.path.join(data_dir, "web_score_trend.json"), orient="records", force_ascii=False, indent=4)
price_trend_df.to_json(os.path.join(data_dir, "web_price_trend.json"), orient="records", force_ascii=False, indent=4)

# 3. Generate the interactive Time-Series Library
import json
historical_export = {}
all_tickers = final_df['Ticker'].unique()

# Rebuild a rank-enhanced copy of final_df for historical export
ranked_history_df = final_df.copy()
ranked_history_df['Rank'] = np.nan

for run_date in sorted(ranked_history_df['Date'].dropna().unique()):
    day_mask = ranked_history_df['Date'] == run_date
    day_df = ranked_history_df.loc[day_mask].copy()
    day_df = day_df.sort_values(by='⭐ Composite Score', ascending=False).reset_index()
    day_df['Rank'] = day_df.index + 1
    ranked_history_df.loc[day_df['index'], 'Rank'] = day_df['Rank'].values

for ticker in all_tickers:
    ticker_history = ranked_history_df[ranked_history_df['Ticker'] == ticker].copy()
    ticker_history = ticker_history.sort_values(by='Date')
    
    desired_cols = ['Date', 'Current Price', 'Total Value Score', '⭐ Composite Score', 'Rank']
    existing_cols = [col for col in desired_cols if col in ticker_history.columns]
    
    chart_data = ticker_history[existing_cols].dropna(subset=['Current Price']).copy()
    historical_export[ticker] = chart_data.to_dict(orient='records')


# Save the full library into the anchored data directory
with open(os.path.join(data_dir, "web_historical_timeseries.json"), "w", encoding="utf-8") as f:
    json.dump(historical_export, f, ensure_ascii=False, indent=4)

print("Success! JSON panels and interactive Time-Series Library securely routed.")

# --- STOP TIMER ---
end_time = time.time()
execution_time = end_time - start_time
minutes = int(execution_time // 60)
seconds = execution_time % 60

print(f"Success! The database has been updated and formatted in {output_filename}.")
print(f"⏱️ Total execution time: {minutes} minutes and {seconds:.2f} seconds.")

# =========================================================
# 10. BACKGROUND LOGGING & EXCEL OPENER
# =========================================================
from datetime import datetime
now = datetime.now()
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
log_message = f"[{timestamp}] SUCCESS | Scraped {len(today_df)} stocks | Time: {minutes}m {seconds:.2f}s\n"

with open("scraper_log.txt", "a", encoding="utf-8") as log_file:
    log_file.write(log_message)

QUIET_MODE = False  

if not QUIET_MODE:
    print("\n🎉 Web deployment assets successfully generated locally!")
    print("Files created: web_today_snapshot.json, web_score_trend.json, web_price_trend.json")
    print(f"Risk/Reward Visualization saved as: {plot_filename}")
else:
    print("Quiet mode active. Web-JSON files saved cleanly in the background.")