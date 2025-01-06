import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright

# Function to extract emails from a website with recursive link following
def extract_emails_with_recursion(url, max_depth=2):
    """Extract emails by following links up to a specified depth."""
    visited_links = set()
    emails = set()

    def crawl(link, depth):
        if depth > max_depth or link in visited_links:
            return
        visited_links.add(link)
        try:
            response = requests.get(link, timeout=10)
            response.raise_for_status()
            content = response.text
            emails.update(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content))
            soup = BeautifulSoup(content, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if href.startswith('/'):
                    href = url + href
                if href.startswith('http'):
                    crawl(href, depth + 1)
        except requests.RequestException:
            pass

    crawl(url, 0)
    return list(emails)

# Function to search Instagram handles using instascrape-like logic
def search_instagram_with_instascrape(name):
    """Search Instagram profiles programmatically."""
    search_url = f"https://www.instagram.com/web/search/topsearch/?query={name}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'x-csrftoken': 'your_csrf_token_here',
    }
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        json_data = response.json()
        for user in json_data.get('users', []):
            if name.lower() in user['user']['username'].lower():
                return f"@{user['user']['username']}"
    except (requests.RequestException, KeyError):
        pass
    return None

# Load the boutiques dataset
file_path = 'final_boutiques.csv'
boutiques_data = pd.read_csv(file_path)

# Update the dataset
for index, row in boutiques_data.iterrows():
    website = row['Website URL']
    boutique_name = row['Boutique Name']

    # Process email extraction if empty
    if pd.isna(row['Email']):
        emails = []
        # Try extracting from website recursively
        if isinstance(website, str):
            emails = extract_emails_with_recursion(f"http://{website.strip()}")
        if emails:
            boutiques_data.at[index, 'Email'] = emails[0]

    # Process Instagram handle if empty
    if pd.isna(row['Instagram']):
        instagram_handle = search_instagram_with_instascrape(boutique_name)
        if instagram_handle:
            boutiques_data.at[index, 'Instagram'] = instagram_handle

# Save the updated data back to CSV
output_path = 'final_boutiques_updated.csv'
boutiques_data.to_csv(output_path, index=False)

print(f"Updated file saved to: {output_path}")
