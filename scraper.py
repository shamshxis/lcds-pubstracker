import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
# (Keep your existing configuration here)
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Pubs-Tracker/2.0 (mailto:{mailto})'}

# --- HELPER FUNCTIONS ---

def get_staff_list():
    """Scrapes the LCDS People page for current staff with better selectors."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list from {url}...")
    
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # STRATEGY 1: Look for specific 'Profile' links which usually contain the full name
        # This is often the most reliable way to get names without titles like "Dr" or "Prof"
        for link in soup.select('a[href^="/people/"]'):
            name = link.get_text(strip=True)
            # Filter out junk links like "More people" or empty strings
            if name and len(name.split()) >= 2 and "View profile" not in name:
                names.add(name)

        # STRATEGY 2: Look for Heading tags often used for names in grid views
        # (h2, h3, h4 with specific classes often used in Drupal/Oxford sites)
        selectors = [
            'h3.node__title',                # Common Drupal teaser title
            '.views-field-title',            # Common Views field
            '.profile-title',                # Specific profile class
            'div.field-content a'            # Generic field content link
        ]
        
        for s in selectors:
            for el in soup.select(s):
                n = el.get_text(strip=True)
                if n and len(n.split()) >= 2:
                    names.add(n)

        # Clean up names (remove titles if they got stuck, though OpenAlex handles them okay)
        clean_names = []
        for n in names:
            # excessive cleaning not needed for OpenAlex, but good to trim
            clean_names.append(n.strip())
            
        final_list = sorted(list(set(clean_names)))
        
        print(f"[{datetime.now().time()}] Successfully found {len(final_list)} staff members.")
        return final_list

    except Exception as e:
        print(f"[ERROR] Failed to scrape staff list: {e}")
        # FALLBACK: If scraping fails entirely, returning an empty list is better 
        # than a fake one so you know it failed.
        return []

# ... (The rest of your code: get_affiliation_status, fetch_openalex_data, main execution) ...
