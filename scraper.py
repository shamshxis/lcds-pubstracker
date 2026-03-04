import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Strict-Affiliation/2.0 (mailto:{mailto})'}

# --- 1. STAFF DISCOVERY ---
def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', '.views-field-title a']
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                if clean and len(clean.split()) >= 2 and len(clean) < 30:
                    names.add(clean)
        staff = sorted(list(names))
        print(f"Found {len(staff)} names on website.")
        return staff
    except: return []

# --- 2. AFFILIATION CHECK (The Filter) ---
def get_verified_orcid(name):
    """
    Finds ORCID but REJECTS unless explicitly linked to LCDS/Demography.
    """
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code != 200: return None
        
        candidates = r.json().get('results', [])
        
        for cand in candidates:
            # Gather Evidence (Affiliations + Topics)
            affs = [a.get('institution', {}).get('display_name', '').lower() for a in cand.get('affiliations', [])]
            last = cand.get('last_known_institution', {}).get('display_name', '').lower()
            topics = [t.get('display_name', '').lower() for t in cand.get('topics', [])]
            
            # Combine into one string for checking
            evidence = f"{last} {' '.join(affs)} {' '.join(topics)}"
            
            # --- 1. THE BAN LIST (Engineers/Chemists) ---
            # Even if they are at Oxford, if they do these things, they are the wrong person.
            bad_flags = [
                'chemistry', 'materials', 'engineering', 'energy', 'catalysis', 
                'polymer', 'nanotechnology', 'physics', 'astronomy', 'optics'
            ]
            if any(bad in evidence for bad in bad_flags):
                continue # Skip this candidate immediately
            
            # --- 2. THE REQUIRED LIST (Strictly LCDS) ---
            # They MUST match one of these to be accepted.
            good_flags = [
                'leverhulme', 'lcds', 'demographic science'
            ]
            
            if any(good in evidence for good in good_flags):
                return cand['orcid'].replace('https://orcid.org/', '')
                
        return None
    except: return None

# --- 3. FETCH WORKS ---
def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        # Fetching recent works (2020+) sorted by Created Date (Newest)
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2020-01-01&sort=created&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                title = item.get('title', ['Untitled'])[0]
                
                # --- EXTRA SAFETY: Title Check ---
                # Double check the paper title for obvious engineering terms just in case
                if any(x in title.lower() for x in ['photocatalyst', 'graphene', 'lattice', 'baryon']):
                    continue

                # Date Logic
                date_obj = item.get('created') or item.get('published-online')
                if date_obj and 'date-parts' in date_obj:
                    d = date_obj['date-parts'][0]
                    final_date = "{:04d}-{:02d}-{:02d}".format(*d) if len(d)==3 else "{:04d}-{:02d}-01".format(*d)
                elif date_obj and 'date-time' in date_obj:
                    final_date = str(date_obj['date-time']).split('T')[0]
                else: final_date = datetime.now().strftime('%Y-%m-%d')

                # Journal Name
                container = item.get('container-title', [''])[0]
                if not container: container = "Preprint/Other"
                
                ptype = "Preprint" if (item.get('type') == 'posted-content' or item.get('subtype') == 'preprint') else "Journal Article"

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'Paper Title': title,
                    'Journal Name': container,
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': ptype,
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'].lower().strip()
                })
    except: pass
    return works

def process_author(name):
    orcid = get_verified_orcid(name)
    return fetch_works(name, orcid) if orcid else []

if __name__ == "__main__":
    staff = get_staff_list()
    all_recs = []
    
    # 8 Workers
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(process_author, n): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_recs.extend(res)

    if all_recs:
        df = pd.DataFrame(all_recs)
        df = df.sort_values(by='Date Available Online', ascending=False).drop_duplicates(subset=['DOI_Clean'])
        df.drop(columns=['DOI_Clean'], inplace=True)
        
        for c in ['Date Available Online','LCDS Author','Paper Title','Journal Name','Citation Count','Publication Type','DOI']:
            if c not in df.columns: df[c] = ""
        
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} verified records.")
    else:
        print("No verified records found.")
