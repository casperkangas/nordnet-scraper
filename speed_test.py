from playwright.sync_api import sync_playwright
import time
from datetime import datetime
import math

# =========================================================
# CONFIGURATION
# =========================================================
TEST_STOCKS = {
    "KNEBV": "https://www.nordnet.fi/osakkeet/kurssit/kone-b-knebv-xhel?details",
    "FORTUM": "https://www.nordnet.fi/osakkeet/kurssit/fortum-xhel?details",
    "NESTE": "https://www.nordnet.fi/osakkeet/kurssit/neste-xhel?details"
}

METRICS_TO_KEEP = [
    "P/E", "EPS", "Osinko/osake", "Osinkotuotto", 
    "P/B", "PEG", "P/S", "Liikevaihto", "EBIT"
]

# =========================================================
# SCRAPING ENGINE
# =========================================================
def run_scrape_pass(wait_time_ms):
    """Runs a single scraping pass on the test stocks using a specific wait time."""
    results = {}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Block images, CSS, and fonts to maximize speed
        page.route("**/*", lambda route: route.abort() 
                   if route.request.resource_type in ["image", "stylesheet", "font"] 
                   else route.continue_())

        for ticker, url in TEST_STOCKS.items():
            stock_data = {}
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # ---> THE BOTTLENECK WE ARE TESTING <---
                page.wait_for_timeout(wait_time_ms) 
                
                # 1. Grab Price (Strict Test Mode)
                try:
                    price_element = page.locator("span[class*='typography-title2'][class*='font-extrabold']").first
                    raw_price = price_element.inner_text(timeout=100) # 100ms strict limit
                    clean_price = raw_price.replace(" ", "").replace("\xa0", "").replace(",", ".")
                    stock_data["Current Price"] = float(clean_price)
                except Exception:
                    stock_data["Current Price"] = None
                
                # 2. Grab Metrics
                buttons = page.query_selector_all('button')
                for button in buttons:
                    aria_label = button.get_attribute('aria-label')
                    if aria_label and ":" in aria_label:
                        parts = aria_label.split(":")
                        metric_name = parts[0].strip()
                        if metric_name in METRICS_TO_KEEP:
                            raw_val = parts[1].strip()
                            if "Ei käytettävissä" not in raw_val:
                                clean_val = raw_val.replace("EUR", "").replace("%", "").strip()
                                try:
                                    stock_data[metric_name] = float(clean_val)
                                except ValueError:
                                    stock_data[metric_name] = clean_val
                                    
            except Exception as e:
                pass # Silently fail, the verifier will catch the missing data
            
            results[ticker] = stock_data
            
        browser.close()
    return results

def verify_data_completeness(data):
    """Checks if the data was successfully scraped, ignoring the live fluctuating values."""
    for ticker, metrics in data.items():
        if metrics.get("Current Price") is None:
            return False
        for metric_name in METRICS_TO_KEEP:
            if metric_name not in metrics or metrics[metric_name] is None:
                return False
    return True

# =========================================================
# THE 5x5 DYNAMIC OPTIMIZATION ENGINE
# =========================================================
print("🧪 Starting 5x5 Dynamic Speed Profiler...\n")
test_start_time = time.time()

current_wait = 2000  # Starting at 2000ms
step_down = 50      # Shaving off 50ms each loop
last_safe = 1000
passes_required = 3

print("--- PHASE 1: FINDING THE BREAKING POINT ---")
while current_wait >= 0:
    print(f"\nTesting aggressive speed: {current_wait}ms...")
    success_count = 0
    
    # Run the test 5 times for this specific speed
    for i in range(1, passes_required + 1):
        test_data = run_scrape_pass(current_wait)
        
        if verify_data_completeness(test_data):
            print(f"  -> Pass {i}/{passes_required} OK")
            success_count += 1
            time.sleep(1) # Polite pause to prevent IP throttling
        else:
            print(f"  ❌ FAILED on pass {i}. The site broke at {current_wait}ms.")
            break # Stop testing this speed immediately
            
    # If it survived all 5 passes, it is officially the new safe baseline
    if success_count == passes_required:
        print(f"  ✅ SUCCESS: {current_wait}ms survived all {passes_required} passes.")
        last_safe = current_wait
        current_wait -= step_down
    else:
        break # Exit Phase 1, we found the floor

# 3. The Final Stress Test
print("\n--- PHASE 2: THE FINAL STRESS TEST ---")
optimal_time = last_safe

while True:
    print(f"\nStress testing {optimal_time}ms ({passes_required} consecutive passes)...")
    is_stable = True
    
    for i in range(1, passes_required + 1):
        verify_data = run_scrape_pass(optimal_time)
        
        if not verify_data_completeness(verify_data):
            print(f"  ⚠️ INSTABILITY DETECTED. {optimal_time}ms failed on pass {i}.")
            is_stable = False
            break 
            
        print(f"  -> Stress Pass {i}/{passes_required} OK")
        time.sleep(1.5) 
            
    if is_stable:
        print(f"  ✅ ROCK SOLID. {optimal_time}ms passed the final verification.")
        break
    else:
        # If it fails the stress test, bump the time back up and try again
        optimal_time += step_down
        print(f"  -> Adjusting up to {optimal_time}ms to find stability...")

# =========================================================
# --- CALCULATE BUFFER AND PRINT RESULTS ---
# =========================================================
# Add a 30% safety buffer for real-world network fluctuations
recommended_time = math.ceil(optimal_time * 1.30)

print("\n" + "="*50)
print(f"🏆 OPTIMIZATION COMPLETE")
print(f"Absolute lowest bare-metal time : {optimal_time} ms")
print(f"Recommended production time (+30%) : {recommended_time} ms")
print("="*50 + "\n")
print(f"Action: Open scraper.py and change page.wait_for_timeout(...) to page.wait_for_timeout({recommended_time})")

# =========================================================
# --- BACKGROUND LOGGING ---
# =========================================================
test_end_time = time.time()
total_execution = test_end_time - test_start_time
test_minutes = int(total_execution // 60)
test_seconds = total_execution % 60

now = datetime.now()
timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

# Update the log to save both the raw floor and the safe buffered time
log_message = f"[{timestamp}] PROFILER RUN | Raw Floor: {optimal_time}ms | Recommended: {recommended_time}ms | Test Duration: {test_minutes}m {test_seconds:.2f}s\n"

with open("speed_test_log.txt", "a", encoding="utf-8") as log_file:
    log_file.write(log_message)

print(f"📄 Test results securely logged to speed_test_log.txt")