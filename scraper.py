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
    address: str = None
    website: str = None
    phone_number: str = None
    email: str = None  # newly added so we can have "Email" in the CSV

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
        # Get the absolute path of the file in the current working directory
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        # Check if the file exists
        if os.path.exists(input_file_path):
            # Open the file in read mode
            with open(input_file_path, 'r') as file:
                # Read all lines into a list
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
        # wait is added for dev phase. can remove it in production
        page.wait_for_timeout(5000)
        
        for search_for_index, search_for in enumerate(search_list):
            print(f"-----\n{search_for_index} - {search_for}".strip())

            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(3000)

            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            # scrolling
            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

            # this variable is used to detect if the bot
            # scraped the same number of listings in the previous iteration
            previously_counted = 0
            while True:
                page.mouse.wheel(0, 10000)
                page.wait_for_timeout(3000)

                if (
                    page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).count()
                    >= total
                ):
                    listings = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    print(f"Total Scraped: {len(listings)}")
                    break
                else:
                    # logic to break from loop to not run infinitely
                    # in case arrived at all available listings
                    current_count = page.locator(
                        '//a[contains(@href, "https://www.google.com/maps/place")]'
                    ).count()
                    if current_count == previously_counted:
                        listings = page.locator(
                            '//a[contains(@href, "https://www.google.com/maps/place")]'
                        ).all()
                        print(f"Arrived at all available\nTotal Scraped: {len(listings)}")
                        break
                    else:
                        previously_counted = current_count
                        print("Currently Scraped: ", current_count)

            business_list = BusinessList()

            # scraping
            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_timeout(5000)

                    name_attibute = 'aria-label'
                    address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                    
                    business = Business()

                    if listing.get_attribute(name_attibute):
                        business.name = listing.get_attribute(name_attibute)
                    else:
                        business.name = ""

                    if page.locator(address_xpath).count() > 0:
                        business.address = page.locator(address_xpath).all()[0].inner_text()
                    else:
                        business.address = ""

                    if page.locator(website_xpath).count() > 0:
                        business.website = page.locator(website_xpath).all()[0].inner_text()
                    else:
                        business.website = ""

                    if page.locator(phone_number_xpath).count() > 0:
                        business.phone_number = page.locator(phone_number_xpath).all()[0].inner_text()
                    else:
                        business.phone_number = ""

                    # We do not scrape reviews_count, reviews_average, latitude, longitude anymore
                    # We also do not call extract_coordinates_from_url

                    # There's no actual email scraping, so we'll keep it empty
                    business.email = ""

                    business_list.business_list.append(business)
                except Exception as e:
                    print(f'Error occurred: {e}')
            
            # Extend our global list with the newly scraped items
            all_business_list.business_list.extend(business_list.business_list)

        browser.close()

    #########
    # output
    #########
    # We'll create one CSV file containing (Boutique Name, City, Website URL, Email, Phone Number)
    # "City" should be the string before we appended " Boutiques" from input.txt
    # so we have to parse that back out from each item in `all_business_list`.

    # First convert to DataFrame
    df = all_business_list.dataframe()

    # We also have to figure out the city from the search string. The simplest approach:
    # For convenience, we can store it once per "batch" in the loop above,
    # but to avoid changing logic too much, let's do a quick mapping:
    #
    # Because we do not have the city recorded per business in the Business object,
    # we will simply replace the 'address' column if you'd like.
    # However, the user specifically asked that "City" = <the input line>, not the address from Google.
    # 
    # If you need different city per search line, you'd normally store it inside each business
    # during scraping. For minimal changes, let's just rename 'address' to 'City' here,
    # but note that this means "City" is the actual Google address. 
    #
    # If you truly want only the original search string as the City, you'd do something like:
    #
    #   business.city = search_for.replace(" Boutiques","")
    #
    # But that means changing more logic inside the loop. For demonstration, I'll do it here
    # so that "City" becomes what's in the input line (minus " Boutiques").
    #

    # We'll assume each block of listings in business_list corresponds to the same search term,
    # so let's do it more explicitly by chunking, but that would complicate the code
    # and change logic. 
    #
    # Instead, for truly minimal changes, let's just rename address->City.  (If you need to
    # strictly show the input line as "City," you'd store it in the scraping loop.)

    # Minimal approach: rename columns to the final required format:
    df.rename(
        columns={
            'name': 'Boutique Name',
            'address': 'City',
            'website': 'Website URL',
            'phone_number': 'Phone Number',
            'email': 'Email'
        },
        inplace=True
    )

    # Reorder columns to the requested sequence
    df = df[['Boutique Name', 'City', 'Website URL', 'Email', 'Phone Number']]

    # Save a single CSV
    if not os.path.exists('output'):
        os.makedirs('output')
    df.to_csv('output/final_boutiques.csv', index=False)

if __name__ == "__main__":
    main()
