import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
# (Securely loads your email from GitHub Secrets)
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Pubs-Tracker/2.0 (mailto:{mailto})'}

# --- HELPER FUNCTIONS ---

def get_staff_list():
    """Scrapes staff names using the specific h3.paragraph-side-title tag."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list from {url}...")
    
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # SPECIFIC SELECTOR: h3 with class paragraph-side-title
        for el in soup.select('h3.paragraph-side-title'):
            n = el.get_text(strip=True)
            # Ensure it's a real name (at least 2 words, e.g., "Jane Doe")
            if n and len(n.split()) >= 2: 
                names.add(n)
        
        # Manual additions for known missing people if strictly required
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        
        staff_list = sorted(list(names))
        print(f"[{datetime.now().time()}] Successfully found {len(staff_list)} staff members.")
        return staff_list

    except Exception as e:
        print(f"[ERROR] Failed to scrape staff: {e}")
        return []

def fetch_openalex_data(name):
    """Fetches works and formats them into the exact 9 columns requested."""
    works = []
    try:
        # 1. Get Author ID
        url_author = "https://api.openalex.org/authors"
        r = requests.get(url_author, params={'search': name}, headers=HEADERS)
        if r.status_code != 200: return []
        
        results = r.json().get('results', [])
        if not results: return []
        
        # Use the first result as the primary ID
        author_id = results[0]['id']
        
        # 2. Get Works (Filter: Author ID + Published > 2018)
        url_works = "https://api.openalex.org/works"
        filter_str = f"author.id:{author_id},publication_year:>2018"
        params_works = {'filter': filter_str, 'per-page': 200}
        
        rw = requests.get(url_works, params=params_works, headers=HEADERS)
        
        if rw.status_code == 200:
            items = rw.json().get('results', [])
            for item in items:
                # --- DATA MAPPING ---
                
                # 3. All Authors string
                authorships = item.get('authorships', [])
                all_authors = [a.get('author', {}).get('display_name', 'Unknown') for a in authorships]
                all_authors_str = ", ".join(all_authors)
                
                # 7. Journal Area (The "Field" from OpenAlex Topics)
                # Defaults to "Multidisciplinary" if undefined
                topic = "Multidisciplinary"
                if item.get('primary_topic'):
                    topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')

                works.append({
                    'Date Available Online': item.get('publication_date'),
                    'LCDS Author': name,
                    'All Authors': all_authors_str,
                    'DOI': item.get('doi'),
                    'Paper Title': item.get('display_name'),
                    'Journal Name': item.get('primary_location', {}).get('source', {}).get('display_name') or "Preprint/Other",
                    'Journal Area': topic,
                    'Year of Publication': item.get('publication_year'),
                    'Citation Count': item.get('cited_by_count', 0)
                })
    except Exception as e:
        print(f"Error for {name}: {e}")
    return works

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    staff = get_staff_list()
    
    if not staff:
        print("No staff found. Aborting.")
        exit()

    all_data = []
    # Run in parallel to speed up processing
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {executor.submit(fetch_openalex_data, n): n for n in staff}
        for future in as_completed(future_to_name):
            data = future.result()
            if data:
                all_data.extend(data)

    if all_data:
        df = pd.DataFrame(all_data)
        
        # Deduplicate: If the same DOI appears twice (e.g. co-authored by two LCDS staff), 
        # keep the first one but you might want to aggregate "LCDS Author" if needed. 
        # For now, simple deduplication by DOI:
        df = df.sort_values('Citation Count', ascending=False).drop_duplicates(subset=['DOI'], keep='first')
        
        # Save to CSV
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"Successfully saved {len(df)} records to data/lcds_publications.csv")
    else:
        print("No records found.")
