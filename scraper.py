import requests
from bs4 import BeautifulSoup
import time  # New import to control the speed of our script

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

# 3. Open and read the targets.txt file
with open("targets.txt", "r", encoding="utf-8") as file:
    # This reads the whole file and stores each line as an item in a list
    lines = file.readlines()

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
        
        # Be polite to the server: wait 3 seconds before requesting the next URL
        time.sleep(3)
        
    else:
        print(f"Failed to retrieve {ticker}. Status code: {response.status_code}")

# 8. Print the final Master List to verify
print("\n--- All Scraping Complete ---")
for data in all_stocks_data:
    print(data)