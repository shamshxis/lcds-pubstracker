import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'OxfordSubUnitTracker/8.0 (mailto:{mailto})'}

# --- DATE RANGES ---
# PRIORITY 1: The "Sprint" (Future/Recent) - Aggressive Fetching
# Captures preprints and 2025-2027 papers
SPRINT_START = "2025-01-01"

# PRIORITY 2: The "Marathon" (Archive) - Gentle Fetching
# Captures historical context from Sep 2019 to end of 2024
MARATHON_START = "2019-09-01"
MARATHON_END = "2024-12-31"

def get_staff_list():
    """Scrapes the LCDS People page for ALL staff."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching full staff list...")
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        selectors = [
            'h3.paragraph-side-title', 
            '.views-field-title a', 
            '.person-name',
            'h3.node__title',
            'span.field-content h3'
        ]
        
        for s in selectors:
            for el in soup.select(s):
                raw_name = el.get_text(strip=True)
                clean = raw_name.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                junk_terms = ["View profile", "Read more", "Contact", "Email", "Research"]
                if any(x in clean for x in junk_terms): continue
                
                if clean and len(clean.split()) >= 2 and len(clean) < 40:
                    names.add(clean)
        
        staff_list = sorted(list(names))
        print(f"[{datetime.now().time()}] Found {len(staff_list)} people.")
        return staff_list

    except Exception as e:
        print(f"[ERROR] Failed to scrape staff: {e}")
        return []

def get_orcid(name):
    """Resolves name to ORCID via OpenAlex."""
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results: return results[0]['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

def standardize_date(date_parts):
    """Converts Crossref [YYYY, MM, DD] to YYYY-MM-DD string."""
    try:
        if not date_parts or not isinstance(date_parts, list): return None
        p = date_parts[0]
        if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
        if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
        if len(p) == 1: return "{:04d}-01-01".format(*p)
    except: return None
    return None

def fetch_crossref_batch(name, orcid, date_filter_str):
    """
    Generic fetcher for Crossref.
    date_filter_str example: "from-pub-date:2025-01-01" or "from-pub-date:2019-09-01,until-pub-date:2024-12-31"
    """
    works = []
    if not orcid: return []

    try:
        # Sort by 'created' ensures we see the item the moment it is registered (Preprints)
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},{date_filter_str}&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                # Type Detection
                raw_type = item.get('type', '')
                subtype = item.get('subtype', '')
                pub_type = "Preprint" if (raw_type == 'posted-content' or subtype == 'preprint') else "Journal Article"

                # Date Logic
                date_obj = item.get('created') or item.get('published-online') or item.get('published-print')
                final_date = None
                
                if date_obj and 'date-parts' in date_obj:
                    final_date = standardize_date(date_obj['date-parts'])
                elif date_obj and 'date-time' in date_obj:
                    final_date = str(date_obj['date-time']).split('T')[0]

                if not final_date: final_date = datetime.now().strftime('%Y-%m-%d')

                # Metadata
                title = item.get('title', ['Untitled'])[0]
                journal = item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other"
                auth_list = [f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]
                all_authors = ", ".join(auth_list)

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'All Authors': all_authors,
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'Paper Title': title,
                    'Journal Name': journal,
                    'Journal Area': "Pending",
                    'Year of Publication': final_date.split('-')[0],
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': pub_type,
                    'DOI_Clean': item['DOI'].lower().strip()
                })
    except Exception: pass
    return works

def enrich_topics(records):
    """Bulk fetch topics from OpenAlex."""
    if not records: return []
    dois = [r['DOI_Clean'] for r in records]
    doi_map = {}
    
    def chunker(seq, size):
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))

    for chunk in chunker(dois, 40):
        try:
            doi_filter = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={doi_filter}&per-page=50&select=doi,primary_topic"
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                for item in r.json().get('results', []):
                    d_key = item.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    topic = "Multidisciplinary"
                    if item.get('primary_topic'):
                        topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')
                    doi_map[d_key] = topic
        except: pass

    for r in records:
        if r['DOI_Clean'] in doi_map:
            r['Journal Area'] = doi_map[r['DOI_Clean']]
        else: r['Journal Area'] = "Multidisciplinary"
    return records

def process_author_sprint(name):
    """Phase 1: Recent data only (2025-2027)"""
    orcid = get_orcid(name)
    if not orcid: return []
    # Filter for Sprint
    filter_str = f"from-pub-date:{SPRINT_START}"
    records = fetch_crossref_batch(name, orcid, filter_str)
    return enrich_topics(records)

def process_author_marathon(name):
    """Phase 2: Archive data (2019-2024)"""
    orcid = get_orcid(name)
    if not orcid: return []
    # Filter for Marathon
    filter_str = f"from-pub-date:{MARATHON_START},until-pub-date:{MARATHON_END}"
    records = fetch_crossref_batch(name, orcid, filter_str)
    return enrich_topics(records)

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    if not staff:
        print("No staff found.")
        exit()

    all_records = []

    # --- PHASE 1: THE SPRINT (Recent / High Priority) ---
    print(f"\n>>> PHASE 1: SPRINT ({SPRINT_START}+) with 8 Workers")
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(process_author_sprint, n): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_records.extend(res)
    print(f"Phase 1 Complete. Records so far: {len(all_records)}")

    # --- PHASE 2: THE MARATHON (Archive / Low Priority) ---
    print(f"\n>>> PHASE 2: MARATHON ({MARATHON_START} to {MARATHON_END}) with 3 Workers")
    with ThreadPoolExecutor(max_workers=3) as exc:
        futures = {exc.submit(process_author_marathon, n): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_records.extend(res)
    
    # --- SAVE ---
    if all_records:
        df = pd.DataFrame(all_records)
        df = df.sort_values(by='Date Available Online', ascending=False)
        # Deduplicate (Crucial because ranges might have edge case overlaps)
        df = df.drop_duplicates(subset=['DOI_Clean'], keep='first')
        df = df.drop(columns=['DOI_Clean'])
        
        expected_cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
                         'Paper Title', 'Journal Name', 'Journal Area', 
                         'Year of Publication', 'Citation Count', 'Publication Type']
        
        for c in expected_cols:
            if c not in df.columns: df[c] = ""
            
        df = df[expected_cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"\nSUCCESS: Saved {len(df)} records (Sprint + Marathon).")
    else:
        print("WARNING: No records found.")
        pd.DataFrame(columns=['Date Available Online']).to_csv("data/lcds_publications.csv", index=False)
