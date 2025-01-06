import re
import requests
from bs4 import BeautifulSoup
import pandas as pd

# Load the boutiques dataset
file_path = 'final_boutiques.csv'
boutiques_data = pd.read_csv(file_path)

def extract_emails_from_website(url):
    """Extract email addresses from a website."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        # Search for email patterns in the website content
        emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', response.text))
        return list(emails)
    except requests.RequestException:
        return []

def find_instagram_handle(name):
    """Find Instagram handle using search queries."""
    search_url = f"https://www.google.com/search?q={name.replace(' ', '+')}+Instagram"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Extract Instagram URL from search results
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'instagram.com' in href:
                handle = re.search(r'instagram\.com/([a-zA-Z0-9_.-]+)', href)
                if handle:
                    return f"@{handle.group(1)}"
    except requests.RequestException:
        return None

# Update the dataset
for index, row in boutiques_data.iterrows():
    website = row['Website URL']
    boutique_name = row['Boutique Name']

    # Process email extraction if empty
    if pd.isna(row['Email']) and isinstance(website, str):
        emails = extract_emails_from_website(f"http://{website.strip()}")
        if emails:
            boutiques_data.at[index, 'Email'] = emails[0]

    # Process Instagram handle if empty
    if pd.isna(row['Instagram']):
        instagram_handle = find_instagram_handle(boutique_name)
        if instagram_handle:
            boutiques_data.at[index, 'Instagram'] = instagram_handle

# Save the updated data back to CSV
output_path = 'final_boutiques_updated.csv'
boutiques_data.to_csv(output_path, index=False)

print(f"Updated file saved to: {output_path}")
