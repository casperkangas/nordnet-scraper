import requests
from bs4 import BeautifulSoup

# This script scrapes stock metrics for Nordea Bank (NDA FI) from the Nordnet website.
url = "https://www.nordnet.fi/osakkeet/kurssit/nordea-bank-nda-fi-xhel?details"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    buttons = soup.find_all('button')
    
    # 1. Create an empty dictionary to store all the stock metrics
    stock_data = {}
    
    # We can also add the stock ticker/name manually so we know whose data this is
    stock_data["Ticker"] = "NDA FI"
    
    for button in buttons:
        aria_label = button.get('aria-label')
        
        # 2. Check if it's a data label (contains a colon)
        if aria_label and ":" in aria_label:
            # Split into exactly two parts
            parts = aria_label.split(":")
            
            # The left side is the metric name (e.g., "Liikevaihto")
            metric_name = parts[0].strip()
            
            # The right side is the raw value (e.g., " 25534000000 EUR")
            raw_value = parts[1].strip()
            
            # 3. Clean the data
            if "Ei käytettävissä" in raw_value:
                # If there is no data, we store a Python 'None' (null value)
                clean_value = None 
            else:
                # Remove "EUR", remove "%", and remove any extra spaces
                clean_text = raw_value.replace("EUR", "").replace("%", "").strip()
                
                try:
                    # Convert the cleaned text into a decimal number
                    clean_value = float(clean_text)
                except ValueError:
                    # If it completely fails to convert to a number, save it as text just in case
                    clean_value = clean_text
            
            # 4. Save the cleaned value into our dictionary under its specific name
            stock_data[metric_name] = clean_value
            
    # 5. Print the entire dictionary to verify our data
    print("--- Successfully Scraped Data ---")
    for metric, value in stock_data.items():
        print(f"{metric}: {value}")

else:
    print(f"Failed to retrieve the page. Status code: {response.status_code}")