from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import date
import os
import numpy as np
import glob
from scoring_engine import apply_weighted_scoring
import time
import matplotlib.pyplot as plt

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

# 3. Use glob to find all text files that start with "targets_"
target_files = glob.glob("targets_*.txt")

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
        industry_name = filename.replace("targets_", "").replace(".txt", "").capitalize()
        
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
                # 1. Instruct the browser to go to the URL (Wait until the skeleton loads)
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # 2. THE HARD PAUSE: Tell the open browser to simply wait 3 seconds.
                # This gives Nordnet's JavaScript plenty of time to paint the financial numbers.
                # Use speed_test.py to experiment with this number and find the optimal balance between speed and data completeness.
                page.wait_for_timeout(3000)
                
                # 3. Grab ALL buttons immediately, whether they are hidden menus or financial data
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
                    price_locator = page.locator("span[class*='InstrumentPrice-styles__CurrentPriceTypography']")
                    
                    # --- THE FIX: A cost-free generous timeout for slow-rendering cross-listed stocks ---
                    price_locator.first.wait_for(state="attached", timeout=10000)
                    
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
output_filename = "Stock_Analysis_Master.xlsx"

# 6. INTEGRATE MANUAL ANALYST RATINGS
manual_file = "Manual_Analyst_Ratings.xlsx"

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
    
# =========================================================
# 7. APPLY WEIGHTED SCORING ENGINE
df = apply_weighted_scoring(df)
# =========================================================

# =========================================================
# 8. HISTORY APPENDING & DASHBOARD SEPARATION
# =========================================================

if os.path.exists(output_filename):
    print(f"Found existing {output_filename}. Appending new data...")
    historical_df = pd.read_excel(output_filename, sheet_name='Historical Database')
    final_df = pd.concat([historical_df, df], ignore_index=True)
    final_df = final_df.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
else:
    print(f"No existing file found. Creating a fresh {output_filename}...")
    final_df = df

# Separate ONLY today's data for the Snapshot dashboard
today_str = str(date.today())
today_df = final_df[final_df['Date'] == today_str].copy()
today_df = today_df.sort_values(by="Total Value Score", ascending=False)

# Identify the historical dates for our comparisons
past_dates = sorted(final_df[final_df['Date'] < today_str]['Date'].unique())
last_date = past_dates[-1] if past_dates else None

# =========================================================
# --- GENERATE THE SCORE TREND MATRIX ---
# =========================================================
print("Generating the historical score matrix...")

trend_df = final_df.pivot(index='Ticker', columns='Date', values='Total Value Score').reset_index()

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

# 8. Save the chart as a static image file
plot_filename = f"Risk_Reward_{today_str}.png"
plt.savefig(plot_filename, bbox_inches='tight', dpi=150)
plt.close() # Free up computer memory

print(f"Saved visualization as {plot_filename}")

# =========================================================
# 9. EXCEL FORMATTING, FILTERING, AND CHART GENERATION
# =========================================================
print("Applying dynamic color codes and generating the dashboard...")

def apply_styles(dataframe):
    return dataframe.style\
        .background_gradient(cmap='RdYlGn', subset=['Total Value Score', 'Industry Value Score'], vmin=0, vmax=100)\
        .background_gradient(cmap='RdYlGn', subset=['Analyst Rating'], vmin=1, vmax=5)\
        .background_gradient(cmap='RdYlGn', subset=['Expected Upside'])\
        .background_gradient(cmap='RdYlGn_r', subset=['Risk Spread'])

styled_today = apply_styles(today_df)
styled_final = apply_styles(final_df)

# A specific function to style the new Difference Percentage columns
def apply_diff_styles(styler, df):
    diff_cols = [col for col in df.columns if "Diff %" in col]
    if diff_cols:
        # Color the percentages (Green for positive, Red for negative, capped visually at +/- 20%)
        styler = styler.background_gradient(cmap='RdYlGn', subset=diff_cols, vmin=-20, vmax=20)
        # Format the numbers nicely as percentages (e.g., +5.20%)
        format_dict = {col: "{:+.2f}%" for col in diff_cols}
        styler = styler.format(format_dict, na_rep="")
    return styler

# Apply styles to Score Trend
styled_trend = trend_df.style
past_score_cols = [c for c in recent_past_dates if c in trend_df.columns]
# Keep the 0-100 gradient ONLY for the raw scores
for col in past_score_cols + ['Current Score']:
    styled_trend = styled_trend.background_gradient(cmap='RdYlGn', subset=[col], vmin=0, vmax=100)
# Apply the specific percentage styling to the diff columns
styled_trend = apply_diff_styles(styled_trend, trend_df)

# Apply styles to Price Trend
styled_price_trend = price_trend_df.style
# Notice we DO NOT color the raw historical prices or current prices here, just the diff columns!
styled_price_trend = apply_diff_styles(styled_price_trend, price_trend_df)

with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
    
    # Write the FOUR sheets
    styled_today.to_excel(writer, sheet_name='Today Snapshot', index=False)
    styled_trend.to_excel(writer, sheet_name='Score Trend', index=False) 
    styled_price_trend.to_excel(writer, sheet_name='Price Trend', index=False) 
    styled_final.to_excel(writer, sheet_name='Historical Database', index=False)
    
    workbook = writer.book
    worksheet_today = writer.sheets['Today Snapshot']
    worksheet_trend = writer.sheets['Score Trend'] 
    worksheet_price = writer.sheets['Price Trend'] 
    worksheet_hist = writer.sheets['Historical Database']
    
    # FREEZE PANES AND FILTERS
    worksheet_today.freeze_panes(1, 1)
    worksheet_trend.freeze_panes(1, 1)
    worksheet_price.freeze_panes(1, 1) 
    worksheet_hist.freeze_panes(1, 1)
    
    worksheet_today.autofilter(0, 0, len(today_df), len(today_df.columns) - 1)
    worksheet_trend.autofilter(0, 0, len(trend_df), len(trend_df.columns) - 1)
    worksheet_price.autofilter(0, 0, len(price_trend_df), len(price_trend_df.columns) - 1) 
    worksheet_hist.autofilter(0, 0, len(final_df), len(final_df.columns) - 1)
    
    # AUTO-FIT COLUMN WIDTHS 
    for idx, col in enumerate(today_df.columns):
        data_max = today_df[col].astype(str).str.len().max()
        data_max = 0 if pd.isna(data_max) else data_max
        max_len = int(max(data_max, len(str(col))) + 2)
        worksheet_today.set_column(idx, idx, max_len)
        worksheet_hist.set_column(idx, idx, max_len) 
        
    for idx, col in enumerate(trend_df.columns):
        data_max = trend_df[col].astype(str).str.len().max()
        data_max = 0 if pd.isna(data_max) else data_max
        max_len = int(max(data_max, len(str(col))) + 2)
        worksheet_trend.set_column(idx, idx, max_len)

    for idx, col in enumerate(price_trend_df.columns):
        data_max = price_trend_df[col].astype(str).str.len().max()
        data_max = 0 if pd.isna(data_max) else data_max
        max_len = int(max(data_max, len(str(col))) + 2)
        worksheet_price.set_column(idx, idx, max_len)
    
    # DRAW THE TOP 10 CHART
    chart = workbook.add_chart({'type': 'column'})
    
    ticker_col = today_df.columns.get_loc("Ticker")
    total_col = today_df.columns.get_loc("Total Value Score")
    upside_col = today_df.columns.get_loc("Expected Upside")
    
    chart_rows = min(len(today_df), 10)
    
    chart.add_series({
        'name':       'Total Value Score',
        'categories': ['Today Snapshot', 1, ticker_col, chart_rows, ticker_col],
        'values':     ['Today Snapshot', 1, total_col, chart_rows, total_col],
        'fill':       {'color': '#4CAF50'} 
    })
    
    chart.add_series({
        'name':       'Expected Upside %',
        'categories': ['Today Snapshot', 1, ticker_col, chart_rows, ticker_col],
        'values':     ['Today Snapshot', 1, upside_col, chart_rows, upside_col],
        'fill':       {'color': '#2196F3'} 
    })
    
    chart.set_title({'name': f'Top {chart_rows} Actionable Stocks ({today_str})'})
    chart.set_size({'width': 750, 'height': 400})
    
    worksheet_today.insert_chart(1, len(today_df.columns) + 1, chart)

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

QUIET_MODE = False  # Set to True when running automatically in the background

if not QUIET_MODE:
    print("Opening the dashboard...")
    os.system(f"open '{output_filename}'")
else:
    print("Quiet mode active. Dashboard saved but not opened.")