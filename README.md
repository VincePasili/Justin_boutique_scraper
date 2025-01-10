# Documentation: Google Maps & Email Scraper with Supabase Integration

## Project Overview

This project scrapes data for boutiques from Google Maps, retrieves emails and Instagram handles from their websites, and saves the results to a **Supabase** database. It processes a **large input file** (Google Sheets link) in **chunks** to manage resource usage efficiently. The scraper includes a **resume** feature, ensuring it picks up from where it left off in case of interruptions.

---

## Features

- **Google Maps Scraper**:
  - Scrapes boutique names, cities, phone numbers, and websites.
- **Email and Instagram Scraper**:
  - Retrieves emails from boutique websites and finds Instagram handles using Google search.
- **Supabase Integration**:
  - Stores all scraped data in a PostgreSQL database hosted on Supabase.
- **Chunk-Based Processing**:
  - Processes a configurable number of rows (`CHUNK_SIZE`) at a time.
- **Resume Functionality**:
  - Uses a checkpoint file (`resume_checkpoint.txt`) to continue from the last processed row.

---

## Setup Instructions

### 1. Prerequisites

1. **Python**: Ensure you have Python 3.8 or newer installed.
2. **Supabase Project**: Create a Supabase project at [https://supabase.com](https://supabase.com). Retrieve your `SUPABASE_URL` and `SUPABASE_ANON_KEY`.
3. **Dependencies**:
   - Install the required Python libraries:
     ```bash
     pip install playwright requests beautifulsoup4 validate_email_address supabase-py python-dotenv
     playwright install
     ```

---

### 2. Environment Variables

This project uses `python-dotenv` to manage Supabase credentials and other configuration.

1. Create a `.env` file in the project directory with the following content:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_ANON_KEY=your-anon-key
   CHUNK_SIZE=50
   ```

2. Update the values:
   - Replace `your-project.supabase.co` with your Supabase project's URL.
   - Replace `your-anon-key` with your Supabase project's anonymous key.

---

### 3. Project Structure

Here’s how the project is organized:

```
.
├── scraper.py         # Main script that runs the scraper
├── resume_checkpoint.txt  # (Generated automatically) Keeps track of the last processed row
├── .env               # Environment variables for Supabase and configuration
```

---

### 4. Usage

#### 4.1 Run the Scraper

To start the scraper, run:

```bash
python scraper.py
```

The script will:

1. Fetch rows from the Google Sheet provided in the script.
2. Start scraping from the last unprocessed row (or the first row if running for the first time).
3. Process rows in chunks (default: 50 rows per chunk).
4. Save data to Supabase.

#### 4.2 Stopping & Resuming

- The script saves the current row index in `resume_checkpoint.txt` after processing each row.
- If stopped, the next run will resume from the last saved row.

---

### 5. Retrieving Supabase Credentials

The script retrieves Supabase credentials and other settings from the `.env` file using `python-dotenv`.

Here’s an example of how it works in the script:

```python
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 10))  # Default chunk size is 10 if not provided
```

---

### 6. Customization

#### Change Chunk Size
- Modify the `CHUNK_SIZE` variable in `.env` to process fewer or more rows per chunk.

#### Change Input File
- Update the Google Sheet link in the script with your own public Google Sheet link.

---

## Supabase Table Schema

The scraper expects a table named `boutiques` in Supabase. The script automatically creates this table if it doesn’t exist.

### Table Definition

```sql
CREATE TABLE IF NOT EXISTS boutiques (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    city TEXT,
    phone_number TEXT,
    website TEXT,
    email TEXT,
    instagram TEXT,
    UNIQUE (name, city)
);
```

### Columns

| Column       | Type     | Description                      |
|--------------|----------|----------------------------------|
| `id`         | BIGSERIAL | Auto-incrementing primary key.   |
| `name`       | TEXT      | Boutique name.                  |
| `city`       | TEXT      | City and state (e.g., "New York, NY"). |
| `phone_number` | TEXT    | Phone number of the boutique.   |
| `website`    | TEXT      | Website URL.                    |
| `email`      | TEXT      | Email(s) of the boutique.       |
| `instagram`  | TEXT      | Instagram handle.               |

---

## Logging and Monitoring

The script logs its progress to the console, including:

- Current chunk being processed.
- Row index being processed.
- Number of records scraped from Google Maps and Email/IG.
- Database upsert status.

---

## Notes

- Ensure the Google Sheet link is public and has the format:
  ```
  https://docs.google.com/spreadsheets/d/1B53QuaYaf73VQgNtaFuYO7m4m9CSOEXx52Wc_BKFafI/edit?usp=sharing
  ```
- The script uses `playwright` for browser automation, which requires installing chromium browser drivers using:
  ```bash
  playwright install chromium
  ```
- Also install playwright dependencies using:
  ```bash
  playwright install-deps
  ```

---

## Troubleshooting

### Missing `.env` File
If the `.env` file is missing or incomplete, the script will raise a `KeyError` when trying to fetch `SUPABASE_URL` or `SUPABASE_ANON_KEY`.

### Supabase Errors
Check the console for errors when upserting or retrieving data from Supabase. Ensure your `SUPABASE_URL` and `SUPABASE_ANON_KEY` are correct.

### Large Input Files
If the Google Sheet has a large number of rows, ensure `CHUNK_SIZE` is set appropriately to prevent overloading resources.

---

## Conclusion

This project is designed to efficiently scrape boutique data from Google Maps and websites, saving the results to Supabase while handling large input files and ensuring resumability. Customize the settings in `.env` and run the script to get started!


