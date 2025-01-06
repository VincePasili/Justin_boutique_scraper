from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
import requests
import concurrent.futures
from bs4 import BeautifulSoup

@dataclass
class Business:
    """Holds business data from Google Maps + second pass info."""
    name: str = None
    city: str = None   # from the input line (minus " Boutiques")
    website: str = None
    phone_number: str = None
    email: str = None
    instagram: str = None

@dataclass
class BusinessList:
    """Holds list of Business objects and can save to CSV/Excel."""
    business_list: list[Business] = field(default_factory=list)
    save_at: str = 'output'

    def dataframe(self):
        """Transform business_list to pandas DataFrame."""
        from pandas import json_normalize
        return json_normalize([asdict(b) for b in self.business_list])

    def save_to_excel(self, filename):
        """Saves to Excel."""
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """Saves to CSV."""
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

def scrape_email_and_instagram_requests(biz: Business) -> Business:
    """
    Use requests + BeautifulSoup to find an Email & Instagram link in the boutique's website.
    We parse <a> tags looking for 'mailto:' or 'instagram.com' in the href.
    """
    if not biz.website or not biz.website.startswith(("http://", "https://")):
        # Invalid or missing URL -> skip
        return biz

    try:
        # Fake User-Agent to seem more like a normal browser
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
            )
        }

        # Fetch the page
        resp = requests.get(biz.website, headers=headers, timeout=15, verify=False)
        if resp.status_code == 200 and resp.text:
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Find all <a href="...">
            anchors = soup.find_all("a", href=True)

            # We'll store the first valid email or instagram we find
            found_email = False
            found_instagram = False

            for a in anchors:
                href = a["href"].strip()
                
                # 1) Check if it's a mailto link
                if not found_email and href.lower().startswith("mailto:"):
                    # e.g. href="mailto:someone@example.com"
                    email = href.split("mailto:")[1]
                    biz.email = email
                    found_email = True
                
                # 2) Check if it's an Instagram link
                if not found_instagram and "instagram.com" in href.lower():
                    # We'll do a naive parse for handle
                    split_ig = href.lower().split("instagram.com/")
                    if len(split_ig) > 1:
                        handle = split_ig[1].split("?")[0].rstrip("/")
                        biz.instagram = handle
                        found_instagram = True

                # If we've found both, we can stop early
                if found_email and found_instagram:
                    break

    except Exception as ex:
        print(f"[!] Error scraping {biz.website} with requests: {ex}")
        # We'll just leave email/instagram as None or whatever was default
        return biz

    return biz

def main():
    ########
    # INPUT
    ########
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str, help="Single search string")
    parser.add_argument("-t", "--total", type=int, help="Max number of listings to scrape per search")
    args = parser.parse_args()
    
    if args.search:
        # Append the word "Boutiques"
        search_list = [args.search.strip() + " Boutiques"]
    else:
        # read from input.txt
        input_file_name = 'input.txt'
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        
        if not os.path.exists(input_file_path):
            print('Error: No search argument provided and input.txt does not exist.')
            sys.exit()
        
        with open(input_file_path, 'r') as file:
            raw_lines = file.readlines()
            # Append " Boutiques" to each line
            search_list = [line.strip() + " Boutiques" for line in raw_lines]
                
        if len(search_list) == 0:
            print('Error: No valid lines in input.txt')
            sys.exit()
        
    if args.total:
        total = args.total
    else:
        # If no total is passed, we set the value to a large number
        total = 1_000_000

    # We'll keep track of all businesses across all search terms
    all_business_list = BusinessList()

    ##############
    # FIRST PASS - Scrape Google Maps
    ##############
    with sync_playwright() as p:
        # Launch a single browser instance for Google Maps scraping
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("https://www.google.com/maps", timeout=60000)
        page.wait_for_timeout(5000)
        
        for idx, search_for in enumerate(search_list):
            print(f"--- Search {idx+1}/{len(search_list)}: {search_for} ---")

            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(5000)

            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            # Scrolling in the left panel
            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

            previously_counted = 0
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(5000)

                current_count = page.locator(
                    '//a[contains(@href, "https://www.google.com/maps/place")]'
                ).count()

                if current_count >= total:
                    listings = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    print(f"Total Scraped (limit {total}): {len(listings)}")
                    break
                else:
                    if current_count == previously_counted:
                        listings = page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).all()
                        print(f"Arrived at all available. Total Scraped: {len(listings)}")
                        break
                    else:
                        previously_counted = current_count
                        print(f"Currently Scraped: {current_count}")

            # City name is the search term minus " Boutiques"
            city_name = search_for.replace(" Boutiques", "").strip()
            business_list = BusinessList()

            # For each listing
            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_timeout(4000)

                    name_attr = 'aria-label'
                    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    phone_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'

                    business = Business()
                    business.city = city_name

                    # name
                    if listing.get_attribute(name_attr):
                        business.name = listing.get_attribute(name_attr)
                    else:
                        business.name = ""

                    # website
                    if page.locator(website_xpath).count() > 0:
                        business.website = page.locator(website_xpath).first.inner_text()
                    else:
                        business.website = ""

                    # phone
                    if page.locator(phone_xpath).count() > 0:
                        business.phone_number = page.locator(phone_xpath).first.inner_text()
                    else:
                        business.phone_number = ""

                    # We'll fetch email & instagram in second pass
                    business_list.business_list.append(business)
                except Exception as e:
                    print(f"[!] Error scraping a listing: {e}")

            # Merge into global list
            all_business_list.business_list.extend(business_list.business_list)

        browser.close()

    #############################
    # SECOND PASS - Use requests & BeautifulSoup
    # to fetch email & IG handles (max 5 at once).
    #############################
    businesses_with_websites = all_business_list.business_list

    updated_businesses = []

    # We'll use concurrency to speed up requests, but only 5 at a time
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_biz = {
            executor.submit(scrape_email_and_instagram_requests, biz): biz
            for biz in businesses_with_websites
        }

        for future in concurrent.futures.as_completed(future_to_biz):
            original_biz = future_to_biz[future]
            try:
                updated_biz = future.result()
                updated_businesses.append(updated_biz)
            except Exception as ex:
                print(f"[!] {original_biz.website} caused an exception: {ex}")
                updated_businesses.append(original_biz)

    # Replace our business list with updated info
    all_business_list.business_list = updated_businesses

    #########
    # OUTPUT
    #########
    df = all_business_list.dataframe()

    # Rename columns
    df.rename(
        columns={
            'name': 'Boutique Name',
            'city': 'City',
            'website': 'Website URL',
            'phone_number': 'Phone Number',
            'email': 'Email',
            'instagram': 'Instagram',
        },
        inplace=True
    )

    # Reorder columns
    df = df[['Boutique Name', 'City', 'Website URL', 'Phone Number', 'Email', 'Instagram']]

    # Save to CSV
    if not os.path.exists('output'):
        os.makedirs('output')
    df.to_csv('output/final_boutiques.csv', index=False)

    print("\nDone! Check output/final_boutiques.csv for results.\n")


if __name__ == "__main__":
    main()
