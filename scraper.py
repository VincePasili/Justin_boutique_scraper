import os
import sys
import time
import re
import random
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import csv


import requests
from bs4 import BeautifulSoup

# Playwright
from playwright.sync_api import sync_playwright

# Email validation
from validate_email_address import validate_email

# Supabase

from supabase import create_client, Client

load_dotenv()
###########################
# CONFIGURE SUPABASE HERE
###########################
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

TABLE_NAME = "boutiques_v2"
CHECKPOINT_FILE = "resume_checkpoint.txt"

# Number of rows to process per chunk
CHUNK_SIZE = 10  # <--- ADJUST this as desired


###########################
# 1) CREATE/ENSURE TABLE
###########################
def ensure_table_exists():
    """
    Check if 'boutiques' table exists in Supabase.
    If it doesn't, create it with a unique (name, city) constraint.
    """
    try:
        _ = supabase.table(TABLE_NAME).select("*").limit(1).execute()
        print(f"[DB] Table '{TABLE_NAME}' exists.")
    except Exception:
        print(f"[DB] Table '{TABLE_NAME}' not found; attempting to create it.")
        create_ddl = f"""
        CREATE TABLE IF NOT EXISTS public.{TABLE_NAME} (
            id bigserial PRIMARY KEY,
            name text,
            city text,
            phone_number text,
            website text,
            email text,
            instagram text,
            UNIQUE (name, city)
        );
        """
        try:
            supabase.rpc("execute_sql", {"sql": create_ddl}).execute()
            print(f"[DB] Created table '{TABLE_NAME}'.")
        except Exception as exc:
            print(f"[DB] Error creating table: {exc}")
            sys.exit(1)


###########################
# 2) LOADING SHEET + RESUME
###########################
def load_google_sheet_rows(sheet_url):
    """
    Given a shareable Google Sheet link, transform it to a CSV export link,
    then fetch and parse line by line.
    The sheet has a single column with header: city,state_id
    So each row has data like "New York,NY".
    Returns a list of tuples [(city, state_id), (city, state_id), ...].
    """
    csv_url = sheet_url.replace("/edit?usp=sharing", "/export?format=csv")

    print(f"[Sheet] Fetching CSV from {csv_url} ...")
    resp = requests.get(csv_url)
    resp.raise_for_status()  # Raise an error if not 200 OK

    decoded_content = resp.content.decode("utf-8", errors="ignore")
    lines = decoded_content.splitlines()
    reader = csv.reader(lines)

    header = next(reader, None)
    if not header:
        print("[Sheet] No header found in the Google Sheet. Exiting.")
        sys.exit(1)

    data = []
    for row in reader:
        if len(row) < 1:
            continue
        # If it's only 1 column, it might be "New York,NY" in one cell
        if len(row) == 1:
            parts = row[0].split(",")
            if len(parts) == 2:
                city, state_id = parts
            else:
                continue
        else:
            # If 2 columns
            city = row[0]
            state_id = row[1] if len(row) > 1 else ""

        data.append((city.strip(), state_id.strip()))

    print(f"[Sheet] Loaded {len(data)} rows from the Google Sheet.")
    return data

def get_resume_index():
    """
    If checkpoint file exists, read the integer stored.
    Else, return 0 (start from first row).
    """
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            idx_str = f.read().strip()
            if idx_str.isdigit():
                return int(idx_str)
    return 0

def update_resume_index(idx: int):
    """
    Overwrite the checkpoint file with the given index.
    """
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        f.write(str(idx))


##########################
# 3) GOOGLE MAPS SCRAPER
##########################
def scrape_google_maps(city: str, state_id: str, headless=True):
    """
    Scrape Google Maps for '{city} {state_id} Boutiques'.
    Return a list of dict: [ {name, city, phone_number, website}, ... ]
    """
    full_search = f"{city} {state_id}".strip() + " Boutiques"
    print(f"[GoogleMaps] Searching for: {full_search}")

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto("https://www.google.com/maps", timeout=60000)
        page.wait_for_timeout(5000)

        page.locator('//input[@id="searchboxinput"]').fill(full_search)
        time.sleep(2)
        page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        # Scroll until no more listings are loaded
        page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')
        previously_counted = 0
        while True:
            page.mouse.wheel(0, 10000)
            page.wait_for_timeout(6000)

            current_count = page.locator(
                '//a[contains(@href, "https://www.google.com/maps/place")]'
            ).count()

            if current_count == previously_counted:
                break
            else:
                previously_counted = current_count

        listings = page.locator(
            '//a[contains(@href, "https://www.google.com/maps/place")]'
        ).all()

        print(f"[GoogleMaps] Found {len(listings)} listings for {city}, {state_id}.")

        for listing in listings:
            try:
                listing.click()
                page.wait_for_timeout(4000)

                name_attr = 'aria-label'
                website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                phone_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'

                record = {}
                record["city"] = f"{city}, {state_id}"
                # name
                nm = listing.get_attribute(name_attr)
                record["name"] = nm if nm else ""

                # website
                if page.locator(website_xpath).count() > 0:
                    record["website"] = page.locator(website_xpath).first.inner_text()
                else:
                    record["website"] = ""

                # phone
                if page.locator(phone_xpath).count() > 0:
                    record["phone_number"] = page.locator(phone_xpath).first.inner_text()
                else:
                    record["phone_number"] = ""

                results.append(record)
            except Exception as e:
                print(f"[GoogleMaps] Error scraping listing: {e}")

        browser.close()

    print(f"[GoogleMaps] {len(results)} records scraped for {city}, {state_id}.")
    return results


###########################
# 4) EMAIL + IG SCRAPER
###########################
EXCLUDED_DOMAINS = {"sentry.wixpress.com", "sentry-next.wixpress.com", "sentry.io"}
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

def is_valid_email(email):
    # Quick naive check to exclude .png, .gif, .jpg
    if any(ext in email.lower() for ext in [".png", ".gif", ".jpg"]):
        return False

    if not validate_email(email, check_format=True, check_blacklist=True, check_dns=True, check_smtp=False):
        return False

    domain = email.split("@")[-1]
    if domain in EXCLUDED_DOMAINS:
        return False

    return True

def sanitize_url(url):
    if url and not (url.startswith("http://") or url.startswith("https://")):
        return f"http://{url}"
    return url

def extract_email_from_website(url):
    """
    Playwright approach first, fallback to requests if that fails.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            time.sleep(random.uniform(2, 5))
            content = page.content()
            emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", content)
            valid_emails = [e for e in emails if is_valid_email(e)]
            browser.close()
            return valid_emails
        except Exception as e:
            print(f"[EmailScraper] Error accessing {url}: {e}")
            browser.close()

            # Fallback
            try:
                print(f"[EmailScraper] Trying fallback for: {url}")
                resp = requests.get(url, timeout=10)
                resp.raise_for_status()
                emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", resp.text)
                valid_emails = [e for e in emails if is_valid_email(e)]
                return valid_emails
            except Exception as fallback_err:
                print(f"[EmailScraper] Fallback failed: {fallback_err}")
                return []

def find_instagram_handle(boutique_name):
    search_url = f"https://www.google.com/search?q={boutique_name.replace(' ', '+')}+Instagram"
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        resp = requests.get(search_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "instagram.com" in href.lower():
                match = re.search(r"instagram\.com/([a-zA-Z0-9_.\-]+)", href, re.IGNORECASE)
                if match:
                    return f"@{match.group(1)}"
    except Exception as e:
        print(f"[IGScraper] Error finding IG for '{boutique_name}': {e}")
    return None

def process_boutique_for_email_and_ig(record):
    website = sanitize_url(record.get("website", ""))
    name = record.get("name", "")

    # 1) Extract emails
    emails = []
    if website:
        print(f"[EmailScraper] Checking {website} for '{name}'")
        emails = extract_email_from_website(website)
    emails = list({e for e in emails if is_valid_email(e)})  # deduplicate

    if emails:
        record["email"] = ", ".join(emails)

    # 2) If no IG handle, try to find it
    if not record.get("instagram"):
        ig = find_instagram_handle(name)
        if ig:
            record["instagram"] = ig

    return record


##############################
# 5) SUPABASE HELPER METHODS
##############################
def upsert_boutiques(data_list):
    """
    Upsert a list of dicts into Supabase. Each record has
    { name, city, phone_number, website, email, instagram }.
    The table has UNIQUE(name, city).
    """
    if not data_list:
        return
    try:
        print(f"[DB] Upserting {len(data_list)} records ...")
        resp = supabase.table(TABLE_NAME).upsert(data_list).execute()
        print(f"[DB] Upsert response: {resp}")
    except Exception as e:
        print(f"[DB] Error upserting: {e}")

def load_boutiques_for_city(city_str):
    """
    Load all records for a given city from Supabase.
    """
    try:
        print(f"[DB] Loading records for city='{city_str}' ...")
        resp = supabase.table(TABLE_NAME).select("*").eq("city", city_str).execute()
        return resp.data if resp.data else []
    except Exception as e:
        print(f"[DB] Error loading records for {city_str}: {e}")
        return []


##########################
# 6) MAIN SCRIPT
##########################
def main():
    ensure_table_exists()

    # The link to your Google Sheet - must be publicly shareable
    sheet_url = (
        "https://docs.google.com/spreadsheets/d/"
        "1B53QuaYaf73VQgNtaFuYO7m4m9CSOEXx52Wc_BKFafI/edit?usp=sharing"
    )

    rows = load_google_sheet_rows(sheet_url)  # returns list of (city, state_id)
    if not rows:
        print("[Main] No rows found in the sheet. Exiting.")
        sys.exit(1)

    start_index = get_resume_index()
    print(f"[Main] Resuming from row index={start_index} ...")
    total = len(rows)

    # Process in CHUNK_SIZE increments
    i = start_index
    while i < total:
        chunk_end = i + CHUNK_SIZE
        if chunk_end > total:
            chunk_end = total

        chunk = rows[i:chunk_end]
        print(f"\n[Main] Processing chunk {i} -> {chunk_end-1} (of {total-1} max)")

        # For each row in this chunk
        for j, (city, state_id) in enumerate(chunk, start=i):
            print(f"\n[Main] Row {j} -> {city}, {state_id}")

            # 1) Scrape Google Maps
            gm_data = scrape_google_maps(city, state_id, headless=True)
            # 2) Upsert to DB
            upsert_boutiques(gm_data)
            gm_data.clear()

            # 3) Wait 30s
            print("[Main] Waiting 30s before email/IG scraping...")
            time.sleep(30)

            # 4) Load from DB
            city_str = f"{city}, {state_id}".strip()
            db_records = load_boutiques_for_city(city_str)

            # 5) Email & IG
            if db_records:
                print(f"[Main] Scraping emails & IG for {len(db_records)} records in '{city_str}'")
                with ThreadPoolExecutor(max_workers=5) as executor:
                    updated_records = list(executor.map(process_boutique_for_email_and_ig, db_records))

                # 6) Upsert updated records
                upsert_boutiques(updated_records)
                updated_records.clear()
            else:
                print(f"[Main] No records in DB for '{city_str}' -> skipping email/IG scraping.")

            # 7) Wait 60s
            print("[Main] Done with this city. Waiting 120s before next city...")
            time.sleep(120)

            # 8) Update resume index after each row
            update_resume_index(j + 1)

        # Done with this chunk
        i = chunk_end

        # Optionally pause between chunks if you like
        if i < total:
            print(f"[Main] Finished chunk up to row {i-1}. Waiting 2 minutes before next chunk...")
            time.sleep(120)
        else:
            print("[Main] No more rows left to process.")

    print("[Main] All done! Exiting.")


if __name__ == "__main__":
    main()
