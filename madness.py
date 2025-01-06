import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright

# Helper function for scraping emails and Instagram handles from a website using Playwright
def extract_emails_and_instagram_with_playwright(url):
    """Extract emails and Instagram handles from a website using Playwright."""
    emails = set()
    instagram_handles = set()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            content = page.content()

            # Extract emails
            emails.update(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content))

            # Extract Instagram handles
            soup = BeautifulSoup(content, 'html.parser')
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'instagram.com' in href:
                    handle = re.search(r'instagram\.com/([a-zA-Z0-9_.-]+)', href)
                    if handle:
                        instagram_handles.add(f"@{handle.group(1)}")

            browser.close()
    except Exception as e:
        print(f"Error scraping {url} with Playwright: {e}")

    return list(emails), list(instagram_handles)

# Helper function for Facebook scraping (Run 2 and 3)
def scrape_email_from_facebook_profile(facebook_url):
    """Scrape email from a Facebook profile using a scraping tool or custom logic."""
    emails = set()
    try:
        response = requests.get(facebook_url, timeout=10)
        response.raise_for_status()
        content = response.text

        # Extract emails
        emails.update(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content))
    except requests.RequestException:
        pass

    return list(emails)

# Helper function for searching Facebook or Google
def search_facebook_or_google_for_email(boutique_name):
    """Search Facebook or Google for the boutique's profile and extract email."""
    search_url = f"https://www.google.com/search?q={boutique_name.replace(' ', '+')}+site:facebook.com"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Find Facebook profile links
        for link in soup.find_all('a', href=True):
            if 'facebook.com' in link['href']:
                emails = scrape_email_from_facebook_profile(link['href'])
                if emails:
                    return emails
    except requests.RequestException as e:
        print(f"Error during search for {boutique_name}: {e}")

    return []

# Load the boutiques dataset
file_path = 'final_boutiques.csv'
boutiques_data = pd.read_csv(file_path)

# Ensure 'Email' and 'Instagram' columns are string types to avoid dtype issues
if 'Email' not in boutiques_data.columns:
    boutiques_data['Email'] = ""
if 'Instagram' not in boutiques_data.columns:
    boutiques_data['Instagram'] = ""

boutiques_data['Email'] = boutiques_data['Email'].astype(str)
boutiques_data['Instagram'] = boutiques_data['Instagram'].astype(str)

# Update the dataset
for index, row in boutiques_data.iterrows():
    website = row['Website URL']
    boutique_name = row['Boutique Name']

    # Run 1: Scrape website for emails and Instagram handles using Playwright
    if not row['Email'] or row['Email'].strip().lower() == "nan":
        if isinstance(website, str) and website.strip():
            print(f"Scraping website for {boutique_name}")
            emails, instagram_handles = extract_emails_and_instagram_with_playwright(f"http://{website.strip()}")
            if emails:
                boutiques_data.at[index, 'Email'] = emails[0]
            if instagram_handles:
                boutiques_data.at[index, 'Instagram'] = instagram_handles[0]

    # Run 2: Scrape Facebook profile if email is still missing
    if not row['Email'] or row['Email'].strip().lower() == "nan":
        print(f"Scraping Facebook profile for {boutique_name}")
        facebook_email = scrape_email_from_facebook_profile(f"https://www.facebook.com/{boutique_name.replace(' ', '')}")
        if facebook_email:
            boutiques_data.at[index, 'Email'] = facebook_email[0]

    # Run 3: Search Facebook or Google for the boutique's profile
    if not row['Email'] or row['Email'].strip().lower() == "nan":
        print(f"Searching Facebook or Google for {boutique_name}")
        searched_emails = search_facebook_or_google_for_email(boutique_name)
        if searched_emails:
            boutiques_data.at[index, 'Email'] = searched_emails[0]

# Save the updated data back to CSV
output_path = 'madness.csv'
boutiques_data.to_csv(output_path, index=False)

print(f"Updated file saved to: {output_path}")

