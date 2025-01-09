import csv
import re
import time
import random
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests
from concurrent.futures import ThreadPoolExecutor
from validate_email_address import validate_email

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
                "email": row.get("Email", "")
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
    return validate_email(email, check_format=True, check_blacklist=True, check_dns=True, check_smtp=False)

# Extract email addresses from a given URL using Playwright
def extract_email_from_website(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
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
            return []

# Extract Facebook profile link from a given website
def extract_facebook_link_from_website(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            time.sleep(random.uniform(2, 5))  # Random delay to mimic human behavior
            content = page.content()
            soup = BeautifulSoup(content, "html.parser")
            links = [a['href'] for a in soup.find_all("a", href=True) if "facebook.com" in a['href']]
            browser.close()
            return links[0] if links else None
        except Exception as e:
            print(f"Error accessing {url}: {e}")
            browser.close()
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

    # Step 2: If no emails found, attempt to retrieve Facebook profile and scrape emails
    if not emails:
        facebook_link = extract_facebook_link_from_website(website)
        if facebook_link:
            print(f"Found Facebook profile: {facebook_link}")
            emails = extract_email_from_website(facebook_link)

    # Deduplicate and validate emails
    emails = list(set(email for email in emails if is_valid_email(email)))

    # Update boutique data
    boutique['email'] = ", ".join(emails) if emails else ""
    return boutique

# Main workflow
def scrape_emails(file_path):
    boutiques = load_csv(file_path)

    with ThreadPoolExecutor(max_workers=5) as executor:
        boutiques = list(executor.map(process_boutique, boutiques))

    print(f"Processed {len(boutiques)} boutiques.")  # Debugging
    return boutiques

# Save results to CSV
def save_results(boutiques, output_file):
    with open(output_file, "w", newline="") as file:
        fieldnames = ["Boutique Name", "City", "Website URL", "Email"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for boutique in boutiques:
            writer.writerow({
                "Boutique Name": boutique['name'],
                "City": boutique['location'],
                "Website URL": boutique['website'],
                "Email": boutique['email']
            })

# Run the script
file_path = "final_boutiques.csv"
output_file = "scraped_emails.csv"
boutiques = scrape_emails(file_path)
save_results(boutiques, output_file)
print(f"Scraping complete. Results saved to {output_file}.")
