import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'OxfordSubUnitTracker/SmartScore/1.0 (mailto:{mailto})'}

# --- 1. STAFF DISCOVERY ---
def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', 'div.person-name', 'span.field-content h3', '.views-field-title a']
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                # strict length check to avoid capturing sentences
                if clean and len(clean.split()) >= 2 and len(clean) < 30:
                    names.add(clean)
        return sorted(list(names))
    except: return []

# --- 2. SMART ORCID RESOLUTION (The Fix) ---
def get_smart_orcid(name):
    """
    Scores potential authors to distinguish the Demographer from the Chemist.
    """
    try:
        # Search for the name
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code != 200: return None
        
        candidates = r.json().get('results', [])
        best_score = -50
        best_orcid = None
        
        for cand in candidates:
            score = 0
            
            # Combine all affiliation text
            affs = [a.get('institution', {}).get('display_name', '').lower() for a in cand.get('affiliations', [])]
            last = cand.get('last_known_institution', {}).get('display_name', '').lower()
            topics = [t.get('display_name', '').lower() for t in cand.get('topics', [])]
            full_text = " ".join(affs + [last] + topics)
            
            # --- SCORING RULES ---
            # 1. POSITIVE (The Right Dept)
            if 'demography' in full_text: score += 10
            if 'population' in full_text: score += 10
            if 'sociology' in full_text: score += 10
            if 'leverhulme' in full_text: score += 15
            if 'nuffield' in full_text: score += 5
            if 'oxford' in full_text: score += 5
            
            # 2. NEGATIVE (The Wrong Dept - The "Chemistry Filter")
            if 'chemistry' in full_text: score -= 100
            if 'engineering' in full_text: score -= 100
            if 'physics' in full_text: score -= 100
            if 'clinical medicine' in full_text: score -= 50
            
            # 3. TOPIC CHECK (If available)
            if any(t in full_text for t in ['fertility', 'mortality', 'migration', 'census']):
                score += 5

            # Select if this is the best valid match so far
            if score > best_score and score > 0: # Must be positive to count
                best_score = score
                best_orcid = cand['orcid'].replace('https://orcid.org/', '')

        return best_orcid
    except: return None

# --- 3. CROSSREF FETCH (Recent & Preprints) ---
def standardize_date(d):
    try:
        if isinstance(d, list): return "{:04d}-{:02d}-{:02d}".format(*d[0]) if len(d[0])==3 else "{:04d}-{:02d}-01".format(*d[0])
        return str(d).split('T')[0]
    except: return datetime.now().strftime('%Y-%m-%d')

def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        # Sort by CREATED to catch "last week's" papers/preprints
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2020-01-01&sort=created&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                # Strict Type
                ptype = "Preprint" if (item.get('type') == 'posted-content' or item.get('subtype') == 'preprint') else "Journal Article"
                
                # Strict Date
                date_obj = item.get('created') or item.get('published-online') or item.get('published-print')
                final_date = standardize_date(date_obj['date-parts'] if date_obj and 'date-parts' in date_obj else date_obj)
                
                # Get Container (Journal Name)
                container = item.get('container-title', [''])[0]
                if not container: container = item.get('institution', {}).get('name') # Preprints
                if not container: container = "Preprint/Other"

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
    # 1. Smart Resolve (Avoids Chemists)
    orcid = get_smart_orcid(name)
    if not orcid: return []
    # 2. Fetch
    return fetch_works(name, orcid)

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    print(f"Scanning {len(staff)} authors (Smart Affiliation Mode)...")
    
    all_records = []
    # 8 Workers is safe
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
        
        # Fill missing cols
        for c in ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 'Citation Count', 'Publication Type', 'DOI']:
            if c not in df.columns: df[c] = ""
            
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found.")
        pd.DataFrame(columns=['Date Available Online']).to_csv("data/lcds_publications.csv", index=False)
