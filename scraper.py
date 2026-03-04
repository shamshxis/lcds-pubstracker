import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'OxfordSubUnitTracker/Final/1.0 (mailto:{mailto})'}

# --- 1. STAFF DISCOVERY (Your Original Logic) ---
def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list from website...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # specific selectors from your original script
        selectors = [
            'h3.paragraph-side-title', 
            'div.person-name', 
            'span.field-content h3', 
            '.views-field-title a'
        ]
        
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                if clean and len(clean.split()) >= 2:
                    names.add(clean)
                    
        return sorted(list(names))
    except Exception as e:
        print(f"Error scraping staff: {e}")
        return []

# --- 2. ORCID RESOLUTION (With STRICT Affiliation Check) ---
def resolve_orcid(name):
    """
    Finds ORCID but ONLY if the person is affiliated with Oxford/Demography.
    This prevents picking up 'John Smith' the engineer.
    """
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            for author in r.json().get('results', []):
                orcid = author.get('orcid')
                if not orcid: continue
                
                # CHECK AFFILIATIONS
                affs = [a.get('institution', {}).get('display_name', '').lower() for a in author.get('affiliations', [])]
                last = author.get('last_known_institution', {}).get('display_name', '').lower()
                all_text = " ".join(affs + [last])
                
                # Your original keywords + specific LCDS terms
                targets = ['oxford', 'leverhulme', 'demographic science', 'nuffield', 'sociology', 'population', 'lcds']
                
                if any(t in all_text for t in targets):
                    return orcid.replace('https://orcid.org/', '')
    except: pass
    return None

# --- 3. DATE STANDARDIZATION ---
def standardize_date(date_obj):
    """Parses Crossref dates robustly."""
    try:
        # Handle date-parts [2024, 1, 15]
        if 'date-parts' in date_obj:
            p = date_obj['date-parts'][0]
            if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
            if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
            if len(p) == 1: return "{:04d}-01-01".format(*p)
        # Handle timestamp string
        if 'date-time' in date_obj:
            return str(date_obj['date-time']).split('T')[0]
    except: pass
    return None

# --- 4. CROSSREF FETCH (Pure Source) ---
def fetch_crossref(name, orcid):
    works = []
    if not orcid: return []

    try:
        # Fetch recent 50 items, sort by CREATED to catch preprints immediately
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2020-01-01&sort=created&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                # --- TYPE DETECTION ---
                ptype = "Preprint" if (item.get('type') == 'posted-content' or item.get('subtype') == 'preprint') else "Journal Article"

                # --- DATE LOGIC ---
                # Priority: Created (Minted) -> Published Online -> Published Print
                date_obj = item.get('created') or item.get('published-online') or item.get('published-print')
                final_date = standardize_date(date_obj)
                if not final_date: final_date = datetime.now().strftime('%Y-%m-%d')

                # --- JOURNAL / CONTAINER ---
                # This replaces "Journal Area". We use the actual Journal Name.
                container = item.get('container-title', [''])[0]
                if not container:
                    container = item.get('institution', {}).get('name') # Sometimes preprints store it here
                if not container:
                    container = "Preprint/Working Paper"

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'All Authors': ", ".join([f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]),
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Journal Name': container,
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': ptype,
                    'DOI_Clean': item['DOI'].lower().strip()
                })
    except: pass
    return works

def process_author(name):
    orcid = resolve_orcid(name)
    if not orcid: return []
    return fetch_crossref(name, orcid)

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    print(f"Scanning {len(staff)} affiliated authors...")
    all_records = []
    
    # 8 Workers is safe for this lighter, filtered workload
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(process_author, n): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_records.extend(res)

    if all_records:
        df = pd.DataFrame(all_records)
        df = df.sort_values(by='Date Available Online', ascending=False)
        df = df.drop_duplicates(subset=['DOI_Clean'], keep='first')
        df = df.drop(columns=['DOI_Clean'])
        
        # Ensure consistency
        cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
                'Paper Title', 'Journal Name', 'Citation Count', 'Publication Type']
        for c in cols:
            if c not in df.columns: df[c] = ""
            
        df = df[cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found.")
