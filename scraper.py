import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Pubs-Tracker/3.0 (mailto:{mailto})'}

def get_staff_list():
    """Scrapes staff names using h3.paragraph-side-title."""
    print(f"[{datetime.now().time()}] Fetching staff list...")
    names = set()
    try:
        # Use a real browser user-agent to avoid blocking
        browser_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get("https://www.demography.ox.ac.uk/people", headers=browser_headers, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for el in soup.select('h3.paragraph-side-title'):
            clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').strip()
            if clean and len(clean.split()) >= 2: 
                names.add(clean)
        
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        return sorted(list(names))
    except Exception as e:
        print(f"[WARN] Staff scrape failed: {e}")
        return ["Ursula Gazeley", "Melinda Mills"]

def resolve_orcid(name):
    """Finds ORCID for a name using OpenAlex."""
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS)
        if r.status_code == 200:
            res = r.json().get('results', [])
            if res: return res[0]['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

def fetch_openalex_data(name):
    """Bulk historical fetch (Good for Topics, bad for recent dates)."""
    works = {}
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS)
        if r.status_code != 200 or not r.json().get('results'): return {}
        
        author_id = r.json()['results'][0]['id']
        # Fetch last 10 years to be safe
        filter_str = f"author.id:{author_id},publication_year:>2019"
        
        rw = requests.get("https://api.openalex.org/works", params={'filter': filter_str, 'per-page': 200}, headers=HEADERS)
        if rw.status_code == 200:
            for item in rw.json().get('results', []):
                doi = item.get('doi')
                if not doi: continue
                
                # Standardize DOI
                doi = doi.replace('https://doi.org/', '').lower().strip()
                
                topic = "Multidisciplinary"
                if item.get('primary_topic'):
                    topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')

                # Store by DOI for easy merging later
                works[doi] = {
                    'Date Available Online': item.get('publication_date'),
                    'LCDS Author': name,
                    'All Authors': ", ".join([a['author']['display_name'] for a in item.get('authorships', [])]),
                    'DOI': f"https://doi.org/{doi}",
                    'Paper Title': item.get('display_name'),
                    'Journal Name': item.get('primary_location', {}).get('source', {}).get('display_name') or "Preprint/Other",
                    'Journal Area': topic,
                    'Year of Publication': item.get('publication_year'),
                    'Citation Count': item.get('cited_by_count', 0),
                    'Publication Type': "Preprint" if item.get('type') in ['preprint', 'posted-content'] else "Journal Article",
                    'Source': 'OpenAlex'
                }
    except Exception as e:
        print(f"[WARN] OpenAlex Error for {name}: {e}")
    return works

def fetch_recent_crossref(name, orcid):
    """Recent fetch (Good for dates, bad for Topics)."""
    works = {}
    if not orcid: return {}
    
    try:
        # Sort by 'published' desc to get the absolute newest items first
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{datetime.now().year-1}&sort=published&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=15)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                doi = item['DOI'].lower().strip()
                
                # --- ROBUST DATE LOGIC ---
                # 1. Try 'published-online' (usually most accurate for recent)
                # 2. Try 'published-print'
                # 3. Try 'issued'
                # 4. Fallback: 'created' (When the DOI was registered - usually same day as online)
                date_source = item.get('published-online') or item.get('published-print') or item.get('issued')
                
                final_date = None
                if date_source and 'date-parts' in date_source:
                    parts = date_source['date-parts'][0]
                    if len(parts) == 3:
                        final_date = f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
                    elif len(parts) == 2:
                        final_date = f"{parts[0]}-{parts[1]:02d}-01"
                    else:
                        final_date = f"{parts[0]}-01-01"
                
                # If date is vague (Jan 1st) or missing, use 'created' timestamp for accuracy
                if not final_date or final_date.endswith('-01-01'):
                    try:
                        created = item.get('created', {}).get('date-time', '')
                        if created:
                            final_date = created.split('T')[0] # Extract YYYY-MM-DD from ISO string
                    except: pass

                if not final_date:
                    final_date = datetime.now().strftime('%Y-%m-%d') # Absolute fallback

                # Type logic
                subtype = item.get('subtype', '')
                w_type = "Preprint" if subtype == 'preprint' or item.get('type') == 'posted-content' else "Journal Article"
                
                works[doi] = {
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'All Authors': ", ".join([f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]),
                    'DOI': f"https://doi.org/{doi}",
                    'Paper Title': item.get('title', [''])[0],
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other",
                    'Journal Area': "Pending (Recent)", 
                    'Year of Publication': final_date.split('-')[0],
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'Source': 'Crossref'
                }
    except Exception as e:
        print(f"[WARN] Crossref Error for {name}: {e}")
    return works

def process_author(name):
    # 1. Get OpenAlex Data (The Baseline)
    oa_data = fetch_openalex_data(name)
    
    # 2. Get Crossref Data (The Updates)
    orcid = resolve_orcid(name)
    cr_data = fetch_recent_crossref(name, orcid)
    
    # 3. SMART MERGE
    # We start with OpenAlex. If Crossref has the same DOI, we OVERWRITE the Date and Title 
    # (because Crossref is newer), but we KEEP the 'Journal Area' from OpenAlex.
    merged = oa_data.copy()
    
    for doi, cr_item in cr_data.items():
        if doi in merged:
            # ENTRY EXISTS: Update it with fresh Crossref data
            merged[doi]['Date Available Online'] = cr_item['Date Available Online']
            merged[doi]['Paper Title'] = cr_item['Paper Title']
            merged[doi]['Publication Type'] = cr_item['Publication Type']
            # We do NOT overwrite 'Journal Area' so we keep the rich topic info
        else:
            # NEW ENTRY: Add it
            merged[doi] = cr_item
            
    return list(merged.values())

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_records = []
    if staff:
        print(f"Scanning {len(staff)} authors with Smart Merge...")
        with ThreadPoolExecutor(max_workers=5) as exc:
            futures = {exc.submit(process_author, n): n for n in staff}
            for f in as_completed(futures):
                try:
                    all_records.extend(f.result())
                except Exception as e:
                    print(f"[CRITICAL] Thread failed: {e}")
    
    # Create CSV
    if all_records:
        df = pd.DataFrame(all_records)
        # Final Sort by Date
        df = df.sort_values(by='Date Available Online', ascending=False)
        
        # Ensure strict column order
        cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 'Paper Title', 
                'Journal Name', 'Journal Area', 'Year of Publication', 'Citation Count', 'Publication Type']
        
        # Fill missing cols if any
        for c in cols:
            if c not in df.columns: df[c] = ""
            
        df = df[cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found.")
        # Create empty
        pd.DataFrame(columns=['Date Available Online']).to_csv("data/lcds_publications.csv", index=False)
