import requests
from bs4 import BeautifulSoup
import time  # New import to control the speed of our script
import pandas as pd
from datetime import date
import os
import numpy as np
import glob

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

# --- DEBUGGING LINES ---
print(f"DEBUG: Found these files: {target_files}")
# -----------------------

if not target_files:
    print("No target files found! Make sure they are named like 'targets_finance.txt'")

# 4. The Outer Loop: Go through every text file found
for file_path in target_files:
    
    # Extract the industry name from the filename
    # Example: "targets_finance.txt" becomes "Finance"
    filename = os.path.basename(file_path)
    industry_name = filename.replace("targets_", "").replace(".txt", "").capitalize()
    
    print(f"\n--- Processing Industry: {industry_name} ---")
    
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()
        
        # --- DEBUGGING LINE ---
        print(f"DEBUG: Found {len(lines)} lines inside {filename}")
        # ----------------------

    # 4. The Master Loop: Go through each line in the text file
    for line in lines:
        # Clean up the line (remove hidden newline characters)
        clean_line = line.strip()
        
        # If the line is empty (e.g., an accidental blank line at the end of the file), skip it
        if not clean_line:
            continue 
            
        # Split the line at the comma to separate the Ticker from the URL
        parts = clean_line.split(",")
        ticker = parts[0].strip()
        url = parts[1].strip()
        
        print(f"Scraping data for: {ticker}...")
        
        # 5. Fetch the web page for this specific stock
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            buttons = soup.find_all('button')
            
            # Create a fresh dictionary for THIS specific stock
            stock_data = {}
            stock_data["Ticker"] = ticker
            stock_data["Date"] = str(date.today())
            stock_data["Industry"] = industry_name
            
            # 6. The Inner Loop: Extract the metrics
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
            
            # 7. Add this completed stock dictionary to the Master List
            all_stocks_data.append(stock_data)
            
            # Be polite to the server: wait 1 seconds before requesting the next URL
            time.sleep(1)
            
        else:
            print(f"Failed to retrieve {ticker}. Status code: {response.status_code}")
    
# --- NEW EXCEL EXPORT LOGIC ---

print("\nConverting data to a table...")

# 5. Convert the Master List into a Pandas DataFrame
df = pd.DataFrame(all_stocks_data)

output_filename = "Stock_Analysis_Master.xlsx"

# --- NEW: INTEGRATE MANUAL ANALYST RATINGS ---
manual_file = "Manual_Analyst_Ratings.xlsx"

# Check if your manual file exists in the folder
if os.path.exists(manual_file):
    print(f"Found {manual_file}. Merging analyst scores...")
    
    # Read your manual Excel file into a pandas table
    manual_df = pd.read_excel(manual_file)
    
    # Merge the manual data into the scraped data
    df = pd.merge(df, manual_df, on="Ticker", how="left")
    
    # --- NEW: CALCULATE NORMALIZED ANALYST SCORE ---
    print("Calculating normalized analyst scores...")
    
    # 1. Calculate the Total Analysts
    df["Total Analysts"] = df["Buy"] + df["Hold"] + df["Sell"]
    
    # 2. Calculate the raw total points using the 1-to-5 scale
    df["Total Points"] = (df["Buy"] * 5) + (df["Hold"] * 3) + (df["Sell"] * 1)
    
    # 3. Calculate the Final Score, safely handling division by zero
    df["Analyst Rating"] = np.where(
        df["Total Analysts"] > 0, 
        df["Total Points"] / df["Total Analysts"], 
        None
    )
    
    # 4. Delete the temporary "Total Points" column to keep the Excel file clean
    df = df.drop(columns=["Total Points"])
    
else:
    print(f"Notice: {manual_file} not found. Skipping analyst scores.")
    
# --- NEW: CALCULATE TWO-TIER PERCENTILE SCORES ---
print("Calculating Total and Industry percentile scores...")

for col in metrics_to_keep:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

higher_is_better = ["EPS", "Osinkotuotto", "Liikevaihto", "EBIT", "Omistajia Nordnetissä*", "Analyst Rating"]
lower_is_better = ["P/E", "P/B", "PEG", "P/S"]

# 1. Calculate TOTAL Percentiles (Relative to ALL stocks)
total_score_cols = []
for metric in higher_is_better:
    if metric in df.columns:
        df[f"{metric}_Total_Rank"] = df[metric].rank(ascending=True, pct=True)
        total_score_cols.append(f"{metric}_Total_Rank")
for metric in lower_is_better:
    if metric in df.columns:
        df[f"{metric}_Total_Rank"] = df[metric].rank(ascending=False, pct=True)
        total_score_cols.append(f"{metric}_Total_Rank")

df["Total Value Score"] = (df[total_score_cols].mean(axis=1) * 100).round(2)

# 2. Calculate INDUSTRY Percentiles (Relative ONLY to peers)
ind_score_cols = []
for metric in higher_is_better:
    if metric in df.columns:
        df[f"{metric}_Ind_Rank"] = df.groupby('Industry')[metric].rank(ascending=True, pct=True)
        ind_score_cols.append(f"{metric}_Ind_Rank")
for metric in lower_is_better:
    if metric in df.columns:
        df[f"{metric}_Ind_Rank"] = df.groupby('Industry')[metric].rank(ascending=False, pct=True)
        ind_score_cols.append(f"{metric}_Ind_Rank")

df["Industry Value Score"] = (df[ind_score_cols].mean(axis=1) * 100).round(2)

# 3. Clean up the temporary ranking columns so the Excel file stays neat
df = df.drop(columns=total_score_cols + ind_score_cols)
# ----------------------------------------

# 6. Check if the master file already exists from a previous run
if os.path.exists(output_filename):
    print(f"Found existing {output_filename}. Appending new data...")
    historical_df = pd.read_excel(output_filename)
    
    # Glue and drop duplicates
    final_df = pd.concat([historical_df, df], ignore_index=True)
    final_df = final_df.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
else:
    print(f"No existing file found. Creating a fresh {output_filename}...")
    final_df = df

# --- NEW: EXCEL FORMATTING AND EXPORT ---
print("Applying color codes and saving...")

# 7. Apply the visual styling
# 'RdYlGn' stands for Red-Yellow-Green. 
# vmin and vmax lock the colors strictly to our 0-to-100 scale.
styled_df = final_df.style.background_gradient(
    cmap='RdYlGn', 
    subset=['Total Value Score', 'Industry Value Score'],
    vmin=0, 
    vmax=100
)

# 8. Save the styled table directly to Excel
styled_df.to_excel(output_filename, index=False, engine='openpyxl')

print(f"Success! The database has been updated and formatted in {output_filename}.")

# --- NEW: AUTO-OPEN EXCEL ON MAC ---
print("Opening the dashboard...")
os.system(f"open '{output_filename}'")