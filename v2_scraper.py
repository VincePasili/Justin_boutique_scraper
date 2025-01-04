from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys

@dataclass
class Business:
    """holds business data"""
    name: str = None
    city: str = None  # <-- We now store the input line (minus "Boutiques") here
    website: str = None
    phone_number: str = None

@dataclass
class BusinessList:
    """holds list of Business objects,
    and can save to excel or csv
    """
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        """transform business_list to pandas dataframe
        Returns: pandas dataframe
        """
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """saves pandas dataframe to excel (xlsx) file

        Args:
            filename (str): filename
        """
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"{self.save_at}/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """saves pandas dataframe to csv file

        Args:
            filename (str): filename
        """
        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"{self.save_at}/{filename}.csv", index=False)

def main():
    
    ########
    # input
    ########
    
    # read search from arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    args = parser.parse_args()
    
    if args.search:
        # append the word "Boutiques"
        search_list = [args.search.strip() + " Boutiques"]
    else:
        search_list = []
        # read search from input.txt file
        input_file_name = 'input.txt'
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        # Check if the file exists
        if os.path.exists(input_file_path):
            with open(input_file_path, 'r') as file:
                raw_lines = file.readlines()
                # Append " Boutiques" to each line
                search_list = [line.strip() + " Boutiques" for line in raw_lines]
                
        if len(search_list) == 0:
            print('Error occurred: You must either pass the -s search argument, or add searches to input.txt')
            sys.exit()
        
    if args.total:
        total = args.total
    else:
        # if no total is passed, we set the value to a large number
        total = 1_000_000

    # We'll store all scraped businesses from all searches into a single object
    all_business_list = BusinessList()

    ###########
    # scraping
    ###########
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto("https://www.google.com/maps", timeout=60000)
        page.wait_for_timeout(5000)
        
        for search_for_index, search_for in enumerate(search_list):
            print(f"-----\n{search_for_index} - {search_for}".strip())

            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(3000)

            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            # scrolling
            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

            # detect if scraping count stalls
            previously_counted = 0
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(3000)

                count_current = page.locator(
                    '//a[contains(@href, "https://www.google.com/maps/place")]'
                ).count()

                if count_current >= total:
                    listings = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    print(f"Total Scraped: {len(listings)}")
                    break
                else:
                    if count_current == previously_counted:
                        listings = page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).all()
                        print(f"Arrived at all available\nTotal Scraped: {len(listings)}")
                        break
                    else:
                        previously_counted = count_current
                        print("Currently Scraped: ", count_current)

            business_list = BusinessList()

            # Prep city name by removing " Boutiques"
            city_name = search_for.replace(" Boutiques", "").strip()

            # scraping
            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_timeout(5000)

                    name_attibute = 'aria-label'
                    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'

                    business = Business()

                    # fill in city from our search string
                    business.city = city_name

                    # name
                    if listing.get_attribute(name_attibute):
                        business.name = listing.get_attribute(name_attibute)
                    else:
                        business.name = ""

                    # website
                    if page.locator(website_xpath).count() > 0:
                        business.website = page.locator(website_xpath).all()[0].inner_text()
                    else:
                        business.website = ""

                    # phone
                    if page.locator(phone_number_xpath).count() > 0:
                        business.phone_number = page.locator(phone_number_xpath).all()[0].inner_text()
                    else:
                        business.phone_number = ""

                    business_list.business_list.append(business)

                except Exception as e:
                    print(f'Error occurred: {e}')
            
            # Extend our global list with the newly scraped items
            all_business_list.business_list.extend(business_list.business_list)

        browser.close()

    #########
    # output
    #########

    # Convert to DataFrame
    df = all_business_list.dataframe()

    # We want only the columns:
    # (Boutique Name, City, Website URL, Phone Number).
    # Rename accordingly:
    df.rename(
        columns={
            'name': 'Boutique Name',
            'city': 'City',
            'website': 'Website URL',
            'phone_number': 'Phone Number'
        },
        inplace=True
    )

    # Reorder columns:
    df = df[['Boutique Name', 'City', 'Website URL', 'Phone Number']]

    # Create a single CSV file
    if not os.path.exists('output'):
        os.makedirs('output')
    df.to_csv('output/final_boutiques.csv', index=False)

if __name__ == "__main__":
    main()
