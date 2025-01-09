import csv
import re
import time
import random
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests
from concurrent.futures import ThreadPoolExecutor
from validate_email_address import validate_email

# List of domains to exclude
EXCLUDED_DOMAINS = {"sentry.wixpress.com","sentry-next.wixpress.com", "sentry.io"}

# Load CSV file and extract boutique names and locations
def load_csv(file_path):
    boutiques = []
    with open(file_path, "r") as file:
        reader = csv.DictReader(file)
        for row in reader:
            boutiques.append({
                "name": row["Boutique Name"],
                "location": row["City"],
                "website": row.get("Website URL", ""),
                "email": row.get("Email", ""),
                "instagram": row.get("Instagram", "")
            })
    print(f"Loaded {len(boutiques)} boutiques from CSV.")  # Debugging
    return boutiques

# Sanitize URLs to ensure they are valid
def sanitize_url(url):
    if url and not url.startswith("http://") and not url.startswith("https://"):
        return f"http://{url}"
    return url

# Rotate User-Agent strings
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
]

# Validate extracted emails using validate-email-address library
def is_valid_email(email):
    if not validate_email(email, check_format=True, check_blacklist=True, check_dns=True, check_smtp=False):
        return False
    domain = email.split("@")[1]
    if domain in EXCLUDED_DOMAINS:
        print(f"Excluded domain detected: {domain}")
        return False
    return True

# Extract email addresses from a given URL using Playwright
# Adds HTTP/2 Protocol Error Handling and fallback
def extract_email_from_website(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-http2"])
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            time.sleep(random.uniform(2, 5))  # Random delay to mimic human behavior
            content = page.content()
            emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content)
            valid_emails = [email for email in emails if is_valid_email(email)]
            browser.close()
            return valid_emails
        except Exception as e:
            print(f"Error accessing {url}: {e}")
            browser.close()

            # Fallback to requests if Playwright fails
            try:
                print(f"Trying fallback for: {url}")
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                emails = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", response.text)
                return [email for email in emails if is_valid_email(email)]
            except requests.RequestException as fallback_error:
                print(f"Fallback failed for {url}: {fallback_error}")
                return []

# Extract Instagram handle using Google search
def find_instagram_handle(name):
    search_url = f"https://www.google.com/search?q={name.replace(' ', '+')}+Instagram"
    headers = {
        'User-Agent': random.choice(USER_AGENTS)
    }
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'instagram.com' in href:
                handle = re.search(r'instagram\.com/([a-zA-Z0-9_.-]+)', href)
                if handle:
                    return f"@{handle.group(1)}"
    except requests.RequestException as e:
        print(f"Error finding Instagram handle for {name}: {e}")
    return None

# Process a single boutique
def process_boutique(boutique):
    name = boutique['name']
    location = boutique['location']
    website = sanitize_url(boutique['website'])
    print(f"Processing: {name} in {location}")

    emails = []

    # Step 1: Visit professional website to scrape emails
    if website:
        print(f"Visiting website: {website}")
        emails = extract_email_from_website(website)

    # Step 2: If no emails found, attempt to retrieve Instagram handle
    if not boutique['instagram']:
        instagram_handle = find_instagram_handle(name)
        if instagram_handle:
            boutique['instagram'] = instagram_handle

    # Deduplicate and validate emails
    emails = list(set(email for email in emails if is_valid_email(email)))

    # Update boutique data
    boutique['email'] = ", ".join(emails) if emails else boutique['email']
    return boutique

# Main workflow
def scrape_emails_and_instagram(file_path):
    boutiques = load_csv(file_path)

    with ThreadPoolExecutor(max_workers=5) as executor:
        boutiques = list(executor.map(process_boutique, boutiques))

    print(f"Processed {len(boutiques)} boutiques.")  # Debugging
    return boutiques

# Save results to CSV
def save_results(boutiques, output_file):
    with open(output_file, "w", newline="") as file:
        fieldnames = ["Boutique Name", "City", "Website URL", "Email", "Instagram"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for boutique in boutiques:
            writer.writerow({
                "Boutique Name": boutique['name'],
                "City": boutique['location'],
                "Website URL": boutique['website'],
                "Email": boutique['email'],
                "Instagram": boutique['instagram']
            })

# Run the script
file_path = "final_boutiques.csv"
output_file = "final_boutiques_updated.csv"
boutiques = scrape_emails_and_instagram(file_path)
save_results(boutiques, output_file)
print(f"Scraping complete. Results saved to {output_file}.")

