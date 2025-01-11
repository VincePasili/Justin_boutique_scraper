import os
import sys
import time
import re
import random
import csv
import fcntl  # For file-based locking on Unix
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from validate_email_address import validate_email
from supabase import create_client, Client
import requests
from bs4 import BeautifulSoup

# -------------------------------------------------------------------
# ENV & CONFIG
# -------------------------------------------------------------------
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

TABLE_NAME = "boutiques"
CHECKPOINT_FILE = "resume_checkpoint.txt"
MIN_SLEEP = 2
MAX_SLEEP = 5
PARALLEL_EMAIL_IG = 5
GOOGLE_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1B53QuaYaf73VQgNtaFuYO7m4m9CSOEXx52Wc_BKFafI/edit?usp=sharing"
)

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
]

EXCLUDED_DOMAINS = {"sentry.wixpress.com", "sentry-next.wixpress.com", "sentry.io"}

# -------------------------------------------------------------------
# HELPER FUNCTIONS
# -------------------------------------------------------------------
def random_human_sleep():
    time.sleep(random.uniform(MIN_SLEEP, MAX_SLEEP))

def get_cities_from_google_sheet(sheet_url: str):
    csv_url = sheet_url.replace("/edit?usp=sharing", "/export?format=csv")
    print(f"[Sheet] Fetching CSV from {csv_url} ...")
    try:
        resp = requests.get(csv_url)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[Sheet] Error fetching sheet: {e}")
        sys.exit(1)

    decoded_content = resp.content.decode("utf-8", errors="ignore")
    lines = decoded_content.splitlines()
    reader = csv.reader(lines)
    header = next(reader, None)
    if not header:
        print("[Sheet] No header found. Exiting.")
        sys.exit(1)

    data = []
    for row in reader:
        if len(row) == 1:
            parts = row[0].split(",")
            if len(parts) == 2:
                data.append((parts[0].strip(), parts[1].strip()))
        elif len(row) >= 2:
            data.append((row[0].strip(), row[1].strip()))
    
    print(f"[Sheet] Loaded {len(data)} city rows.")
    return data

def acquire_lock_and_get_next_city(cities):
    with open(CHECKPOINT_FILE, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
        except Exception as e:
            print(f"[Lock] Error acquiring lock: {e}")
            return None

        f.seek(0)
        content = f.read().strip()
        current_index = int(content) if content.isdigit() else 0

        if current_index >= len(cities):
            fcntl.flock(f, fcntl.LOCK_UN)
            return None

        city, state_id = cities[current_index]
        f.seek(0)
        f.truncate()
        f.write(str(current_index + 1))
        fcntl.flock(f, fcntl.LOCK_UN)
    
    return (current_index, city, state_id)

def scrape_google_maps(city, state_id, headless=True):
    full_search = f"{city.strip()} {state_id.strip()} Boutiques"
    print(f"[GoogleMaps] Searching for: {full_search}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--disable-http2"])
        context = browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = context.new_page()
        page.goto("https://www.google.com/maps", timeout=60000)
        random_human_sleep()

        try:
            page.locator('input#searchboxinput').fill(full_search)
            random_human_sleep()
            page.keyboard.press("Enter")
            random_human_sleep()
        except Exception as e:
            print(f"[GoogleMaps] Error entering search query: {e}")
            browser.close()
            return results

        previously_counted = 0
        while True:
            try:
                page.mouse.wheel(0, 3000)
                random_human_sleep()
                current_count = page.locator('a[href*="https://www.google.com/maps/place"]').count()
                if current_count == previously_counted:
                    break
                previously_counted = current_count
            except Exception as e:
                print(f"[GoogleMaps] Error during scrolling: {e}")
                break

        listings = page.locator('a[href*="https://www.google.com/maps/place"]').all()
        for listing in listings:
            try:
                listing.click()
                random_human_sleep()

                name_attr = listing.get_attribute("aria-label")
                phone_selector = 'button[data-item-id^="phone:tel:"] div.fontBodyMedium'
                website_selector = 'a[data-item-id="authority"] div.fontBodyMedium'

                result = {
                    "name": name_attr.strip() if name_attr else "",
                    "location": f"{city.strip()}, {state_id.strip()}",
                    "Phone": page.locator(phone_selector).first.inner_text().strip() if page.locator(phone_selector).count() else "",
                    "website": page.locator(website_selector).first.inner_text().strip() if page.locator(website_selector).count() else "",
                }
                print(f"[GoogleMaps] Scraped data: {result}")
                results.append(result)
            except Exception as e:
                print(f"[GoogleMaps] Error reading listing: {e}")

        browser.close()

    print(f"[GoogleMaps] Returning {len(results)} results for city={city}, state_id={state_id}")
    return results

def is_valid_email(email):
    if any(ext in email.lower() for ext in [".png", ".gif", ".jpg", ".jpeg"]):
        return False
    if not validate_email(
        email,
        check_format=True,
        check_blacklist=True,
        check_dns=True,
        check_smtp=False
    ):
        return False
    domain = email.split("@")[1]
    return domain not in EXCLUDED_DOMAINS

def extract_email_from_website(url):
    url = f"http://{url}" if not (url.startswith("http://") or url.startswith("https://")) else url
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            random_human_sleep()
            content = page.content()
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content)
            valid_emails = [e for e in emails if is_valid_email(e)]
            print(f"[EmailScraper] Found emails: {valid_emails}")
            browser.close()
            return valid_emails
        except Exception as e:
            print(f"[EmailScraper] Error with playwright on {url}: {e}")
            browser.close()
            return []

def find_instagram_handle(boutique_name):
    query = f"{boutique_name.replace(' ', '+')}+Instagram"
    search_url = f"https://www.google.com/search?q={query}"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "instagram.com" in href.lower():
                match = re.search(r"instagram\.com/([a-zA-Z0-9_.-]+)", href, re.IGNORECASE)
                if match:
                    ig_handle = "@" + match.group(1)
                    print(f"[IGScraper] Found Instagram handle: {ig_handle}")
                    return ig_handle
    except Exception as e:
        print(f"[IGScraper] Error searching IG for '{boutique_name}': {e}")
    return None

def process_boutique_for_email_and_ig(record):
    name = record.get("name", "").strip()
    website = record.get("website", "").strip()

    if website:
        all_emails = extract_email_from_website(website)
        if all_emails:
            record["Email"] = ", ".join(set(all_emails))

    if not record.get("Instagram"):
        ig_handle = find_instagram_handle(name)
        if ig_handle:
            record["Instagram"] = ig_handle

    print(f"[Processor] Updated record: {record}")
    return record

def insert_boutiques_into_db(records):
    if not records:
        print("[DB] No records to insert.")
        return

    try:
        print(f"[DB] Attempting to insert {len(records)} records...")
        resp = supabase.table(TABLE_NAME).upsert(records).execute()
        if resp.status_code == 201:
            print(f"[DB] Successfully inserted {len(records)} records.")
        else:
            print(f"[DB] Insert response: {resp.data}")
    except Exception as e:
        print(f"[DB] Insert error: {e}")

def main():
    city_list = get_cities_from_google_sheet(GOOGLE_SHEET_URL)
    if not city_list:
        print("[Main] No cities found. Exiting.")
        sys.exit(0)

    if not os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "w") as f:
            f.write("0")

    while True:
        nxt = acquire_lock_and_get_next_city(city_list)
        if not nxt:
            print("[Main] All cities processed. Exiting.")
            break

        index, city, state_id = nxt
        print(f"\n[Main] Starting city #{index + 1}: {city}, {state_id}")

        raw_data = scrape_google_maps(city, state_id, headless=True)
        if raw_data:
            print(f"[Main] Scraped {len(raw_data)} records for {city}, {state_id}.")
            insert_boutiques_into_db(raw_data)

            print(f"[Main] Searching for Emails & IG on {len(raw_data)} records for {city}, {state_id}")
            with ThreadPoolExecutor(max_workers=PARALLEL_EMAIL_IG) as executor:
                enriched_data = list(executor.map(process_boutique_for_email_and_ig, raw_data))

            print(f"[Main] Inserting enriched records for {city}, {state_id}.")
            insert_boutiques_into_db(enriched_data)
        else:
            print(f"[Main] No data found for city: {city}, {state_id}")

        print("[Main] Sleeping for 5 minutes before next city...")
        time.sleep(5 * 60)

if __name__ == "__main__":
    main()
