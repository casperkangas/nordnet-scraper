import requests
from bs4 import BeautifulSoup
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
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            buttons = soup.find_all('button')
            
            stock_data = {}
            stock_data["Ticker"] = ticker
            stock_data["Date"] = str(date.today())
            stock_data["Industry"] = industry_name
            
            for button in buttons:
                aria_label = button.get('aria-label')
                
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
            time.sleep(1)   # Let servers breathe and avoid getting blocked
            
        else:
            print(f"Failed to retrieve {ticker}. Status code: {response.status_code}")
    
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
print("Applying color codes and saving...")

styled_df = final_df.style.background_gradient(
    cmap='RdYlGn', 
    subset=['Total Value Score', 'Industry Value Score'],
    vmin=0, 
    vmax=100
)

styled_df.to_excel(output_filename, index=False, engine='openpyxl')
print(f"Success! The database has been updated and formatted in {output_filename}.")

# 10. AUTO-OPEN EXCEL ON MAC
print("Opening the dashboard...")
os.system(f"open '{output_filename}'")