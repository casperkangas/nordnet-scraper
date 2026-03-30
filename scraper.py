from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import date
import os
import numpy as np
import glob
from scoring_engine import apply_weighted_scoring
import time

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
                page.wait_for_timeout(3000) 
                
                # 3. Grab ALL buttons immediately, whether they are hidden menus or financial data
                buttons = page.query_selector_all('button')
                
                stock_data = {}
                stock_data["Ticker"] = ticker
                stock_data["Date"] = str(date.today())
                stock_data["Industry"] = industry_name
                
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
    # Read the historical sheet to ensure we only append to the master record
    historical_df = pd.read_excel(output_filename, sheet_name='Historical Database')
    final_df = pd.concat([historical_df, df], ignore_index=True)
    final_df = final_df.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
else:
    print(f"No existing file found. Creating a fresh {output_filename}...")
    final_df = df

# Separate ONLY today's data for the Snapshot dashboard
today_str = str(date.today())
today_df = final_df[final_df['Date'] == today_str].copy()

# --- NEW: AUTO-SORTING ---
# Sort today's data so your absolute best stocks are always at the top
today_df = today_df.sort_values(by="Total Value Score", ascending=False)

# =========================================================
# 9. EXCEL FORMATTING, FILTERING, AND CHART GENERATION
# =========================================================
print("Applying dynamic color codes and generating the dashboard...")

# Apply the green-to-red styles to both datasets
def apply_styles(dataframe):
    return dataframe.style\
        .background_gradient(cmap='RdYlGn', subset=['Total Value Score', 'Industry Value Score'], vmin=0, vmax=100)\
        .background_gradient(cmap='RdYlGn', subset=['Analyst Rating'], vmin=1, vmax=5)\
        .background_gradient(cmap='RdYlGn', subset=['Expected Upside'])\
        .background_gradient(cmap='RdYlGn_r', subset=['Risk Spread'])

styled_today = apply_styles(today_df)
styled_final = apply_styles(final_df)

# Use XlsxWriter to create the file, add sheets, freeze panes, and draw the chart
with pd.ExcelWriter(output_filename, engine='xlsxwriter') as writer:
    
    # 1. Write the two sheets
    styled_today.to_excel(writer, sheet_name='Today Snapshot', index=False)
    styled_final.to_excel(writer, sheet_name='Historical Database', index=False)
    
    # Access the Excel objects directly
    workbook = writer.book
    worksheet_today = writer.sheets['Today Snapshot']
    worksheet_hist = writer.sheets['Historical Database']
    
    # 2. CREATE THE "TABLE" EXPERIENCE (AutoFilters & Frozen Headers)
    max_col_idx = len(today_df.columns) - 1
    
    # Freeze the top row so headers stay visible when scrolling
    worksheet_today.freeze_panes(1, 1)
    worksheet_hist.freeze_panes(1, 1)
    
    # Add dropdown filter arrows to the top row
    worksheet_today.autofilter(0, 0, len(today_df), max_col_idx)
    worksheet_hist.autofilter(0, 0, len(final_df), max_col_idx)
    
    # 3. DRAW THE TOP 10 CHART
    chart = workbook.add_chart({'type': 'column'})
    
    # Find the column index numbers so the chart knows where to look
    ticker_col = today_df.columns.get_loc("Ticker")
    total_col = today_df.columns.get_loc("Total Value Score")
    upside_col = today_df.columns.get_loc("Expected Upside")
    
    # Determine how many stocks to chart (Up to 10)
    chart_rows = min(len(today_df), 10)
    
    # Add Total Score bars
    chart.add_series({
        'name':       'Total Value Score',
        'categories': ['Today Snapshot', 1, ticker_col, chart_rows, ticker_col],
        'values':     ['Today Snapshot', 1, total_col, chart_rows, total_col],
        'fill':       {'color': '#4CAF50'} # Clean Green
    })
    
    # Add Expected Upside bars
    chart.add_series({
        'name':       'Expected Upside %',
        'categories': ['Today Snapshot', 1, ticker_col, chart_rows, ticker_col],
        'values':     ['Today Snapshot', 1, upside_col, chart_rows, upside_col],
        'fill':       {'color': '#2196F3'} # Clean Blue
    })
    
    # Format the Chart's visuals
    chart.set_title({'name': f'Top {chart_rows} Actionable Stocks ({today_str})'})
    chart.set_size({'width': 750, 'height': 400})
    
    # Insert the chart onto the Snapshot sheet, positioned nicely to the right of your data
    worksheet_today.insert_chart(1, max_col_idx + 2, chart)

# --- STOP TIMER ---
end_time = time.time()
execution_time = end_time - start_time
minutes = int(execution_time // 60)
seconds = execution_time % 60

print(f"Success! The database has been updated and formatted in {output_filename}.")
print(f"⏱️ Total execution time: {minutes} minutes and {seconds:.2f} seconds.")

# 10. AUTO-OPEN EXCEL ON MAC
print("Opening the dashboard...")
os.system(f"open '{output_filename}'")