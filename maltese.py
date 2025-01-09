import csv
import re
import time
import random
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests
from concurrent.futures import ThreadPoolExecutor
from validate_email_address import validate_email
from dataclasses import dataclass, asdict, field
import os
from pandas import json_normalize

# List of domains to exclude
EXCLUDED_DOMAINS = {"sentry.wixpress.com","sentry-next.wixpress.com", "sentry.io"}

@dataclass
class Business:
    """Holds business data from Google Maps + second pass info."""
    name: str = None
    city: str = None
    website: str = None
    email: str = None
    instagram: str = None

@dataclass
class BusinessList:
    """Holds list of Business objects and can save to CSV."""
    business_list: list[Business] = field(default_factory=list)
    save_at: str = 'output'

    def dataframe(self):
        """Transform business_list to pandas DataFrame."""
        return json_normalize([asdict(b) for b in self.business_list])

    def save_to_csv(self, filename):
        """Saves to CSV."""
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

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
        browser = p.chromium.launch(headless=False, args=["--disable-http2"])
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
                headers = {
                    'User-Agent': random.choice(USER_AGENTS),
                    'Referer': 'https://www.google.com/'
                }
                response = requests.get(url, headers=headers, timeout=10)
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

# Process a single business
def process_business(business):
    print(f"Processing: {business.name} in {business.city}")

    if business.website:
        print(f"Scraping website: {business.website}")
        emails = extract_email_from_website(sanitize_url(business.website))
        if emails:
            business.email = ", ".join(emails)

    if not business.instagram:
        instagram_handle = find_instagram_handle(business.name)
        if instagram_handle:
            business.instagram = instagram_handle

    return business

# Main workflow
def scrape_boutiques(search_list, total):
    all_business_list = BusinessList()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for idx, search_for in enumerate(search_list):
            print(f"--- Search {idx+1}/{len(search_list)}: {search_for} ---")
            page.goto("https://www.google.com/maps", timeout=60000)
            page.fill('//input[@id="searchboxinput"]', search_for)
            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
            for listing in listings[:total]:
                try:
                    listing.click()
                    page.wait_for_timeout(3000)

                    business = Business(
                        name=listing.get_attribute('aria-label'),
                        city=search_for.replace(" Boutiques", ""),
                        website=page.locator('//a[@data-item-id="authority"]').text_content()
                    )

                    all_business_list.business_list.append(business)
                except Exception as e:
                    print(f"Error processing listing: {e}")

        browser.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        all_business_list.business_list = list(executor.map(process_business, all_business_list.business_list))

    return all_business_list

# Save to CSV
def save_boutiques_to_csv(business_list, output_file):
    business_list.save_to_csv(output_file)

if __name__ == "__main__":
    search_list = ["New York Boutiques", "Los Angeles Boutiques"]
    total = 10  # Max number of listings per search

    all_businesses = scrape_boutiques(search_list, total)
    all_businesses.save_to_csv("final_boutiques")
    print("Scraping complete.")
