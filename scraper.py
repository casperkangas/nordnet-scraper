from playwright.sync_api import sync_playwright
import time
import pandas as pd
from datetime import date
import os
import numpy as np
import glob
from scoring_engine import apply_weighted_scoring

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
    headless=False # keeps it invisible. Set to False if you want to watch it work!
    browser = p.chromium.launch(headless=True) 
    
    # Create a context that looks like a real Mac computer
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    page = context.new_page()

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
# =========================================================
# This single line replaces all the old complex math!
df = apply_weighted_scoring(df)
# =========================================================

# 8. Check if the master file already exists to append data
if os.path.exists(output_filename):
    print(f"Found existing {output_filename}. Appending new data...")
    historical_df = pd.read_excel(output_filename)
    final_df = pd.concat([historical_df, df], ignore_index=True)
    final_df = final_df.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
else:
    print(f"No existing file found. Creating a fresh {output_filename}...")
    final_df = df

# 9. EXCEL FORMATTING AND EXPORT
print("Applying dynamic color codes and saving...")

# Apply specific color gradients based on the unique scale of each metric
styled_df = final_df.style\
    .background_gradient(
        cmap='RdYlGn', 
        subset=['Total Value Score', 'Industry Value Score'], 
        vmin=0, vmax=100
    )\
    .background_gradient(
        cmap='RdYlGn', 
        subset=['Analyst Rating'], 
        vmin=1, vmax=5
    )\
    .background_gradient(
        cmap='RdYlGn', 
        subset=['Expected Upside']
    )

# Save the styled table directly to Excel
styled_df.to_excel(output_filename, index=False, engine='openpyxl')

print(f"Success! The database has been updated and formatted in {output_filename}.")

# 10. AUTO-OPEN EXCEL ON MAC
print("Opening the dashboard...")
os.system(f"open '{output_filename}'")