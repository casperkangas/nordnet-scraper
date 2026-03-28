import requests
from bs4 import BeautifulSoup

# 1. Define the target URL
url = "https://www.nordnet.fi/osakkeet/kurssit/rheinmetall-rhm-xeta?details"

# 2. Set up headers to look like a normal web browser
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 3. Send the request to the website
response = requests.get(url, headers=headers)

# 4. Check if the request was successful (Status code 200 means OK)
if response.status_code == 200:
    print("Successfully connected to Nordnet!")
    
    # 5. Load the raw HTML into BeautifulSoup for parsing later
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Print a tiny snippet of the raw code just to prove it worked
    print(soup.prettify()[:200]) 
else:
    print(f"Failed to retrieve the page. Status code: {response.status_code}")