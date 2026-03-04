import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
# Loads email from Secrets, defaults to a placeholder if missing
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {
    'User-Agent': f'LCDS-Pubs-Tracker/2.0 (mailto:{mailto})',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
}

def get_staff_list():
    """Scrapes staff names, handling whitespace and newlines in HTML."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list from {url}...")
    
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # TARGETED SELECTOR: h3 with class 'paragraph-side-title'
        for el in soup.select('h3.paragraph-side-title'):
            # .get_text(strip=True) removes leading/trailing whitespace & newlines
            raw_name = el.get_text(strip=True)
            
            # Clean up: sometimes titles like "Dr." or "Prof." stick around
            # We want just the name for the API search. 
            # (OpenAlex is smart, but cleaner is better)
            clean_name = raw_name.replace('Dr ', '').replace('Prof ', '').strip()
            
            if clean_name and len(clean_name.split()) >= 2: 
                names.add(clean_name)
        
        # Manually add anyone who might be missing due to different HTML formatting
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        
        staff_list = sorted(list(names))
        print(f"[{datetime.now().time()}] Successfully found {len(staff_list)} staff members.")
        return staff_list

    except Exception as e:
        print(f"[ERROR] Failed to scrape staff: {e}")
        # Return fallback list so the script continues
        return ["Ursula Gazeley", "Melinda Mills"]

def fetch_openalex_data(name):
    """Fetches works and formats them into the exact 9 columns."""
    works = []
    try:
        # 1. Get Author ID
        url_author = "https://api.openalex.org/authors"
        r = requests.get(url_author, params={'search': name}, headers=HEADERS)
        if r.status_code != 200: return []
        
        results = r.json().get('results', [])
        if not results: return []
        
        # Use first result
        author_id = results[0]['id']
        
        # 2. Get Works
        url_works = "https://api.openalex.org/works"
        filter_str = f"author.id:{author_id},publication_year:>2018"
        params_works = {'filter': filter_str, 'per-page': 200}
        
        rw = requests.get(url_works, params=params_works, headers=HEADERS)
        
        if rw.status_code == 200:
            items = rw.json().get('results', [])
            for item in items:
                authorships = item.get('authorships', [])
                all_authors = [a.get('author', {}).get('display_name', 'Unknown') for a in authorships]
                
                topic = "Multidisciplinary"
                if item.get('primary_topic'):
                    topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')

                works.append({
                    'Date Available Online': item.get('publication_date'),
                    'LCDS Author': name,
                    'All Authors': ", ".join(all_authors),
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
    os.makedirs("data", exist_ok=True)
    
    staff = get_staff_list()
    
    all_data = []
    if staff:
        # ThreadPool for speed
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_name = {executor.submit(fetch_openalex_data, n): n for n in staff}
            for future in as_completed(future_to_name):
                data = future.result()
                if data:
                    all_data.extend(data)

    # Always create CSV (even if empty) to satisfy GitHub Action
    if all_data:
        df = pd.DataFrame(all_data)
        # Deduplicate by DOI
        df = df.sort_values('Citation Count', ascending=False).drop_duplicates(subset=['DOI'], keep='first')
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"Saved {len(df)} records.")
    else:
        print("No records found. Creating empty CSV.")
        # Create empty dataframe with correct columns
        pd.DataFrame(columns=[
            'Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
            'Paper Title', 'Journal Name', 'Journal Area', 'Year of Publication', 'Citation Count'
        ]).to_csv("data/lcds_publications.csv", index=False)
