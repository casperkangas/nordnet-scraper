import requests
from bs4 import BeautifulSoup

url = "https://www.nordnet.fi/osakkeet/kurssit/nordea-bank-nda-fi-xhel?details"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. Find all buttons on the page
    buttons = soup.find_all('button')
    
    # 2. Loop through them to find the one with our specific aria-label
    for button in buttons:
        # Get the aria-label text (if the button doesn't have one, it returns None)
        aria_label = button.get('aria-label')
        
        # 3. Check if the aria-label exists and starts with "P/E:"
        if aria_label and aria_label.startswith("P/E:"):
            print(f"Found the raw label: {aria_label}")
            
            # 4. Split the string at the colon and grab the second part (index 1)
            # Example: "P/E: 10.25" becomes ["P/E", " 10.25"]
            raw_number_string = aria_label.split(":")[1]
            
            # 5. Clean up the extra spaces and convert to a decimal number
            clean_number = float(raw_number_string.strip())
            
            print(f"The precise, mathematical P/E value is: {clean_number}")
            
            # We found what we need, so we can stop the loop
            break 
            
else:
    print(f"Failed to retrieve the page. Status code: {response.status_code}")