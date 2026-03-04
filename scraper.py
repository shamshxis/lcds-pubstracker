import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Nuclear/1.0 (mailto:{mailto})'}

# --- 1. THE BLOCKLIST (The Nuclear Option) ---
# If any of these appear in a Title or Journal, the paper is deleted.
BLACKLIST_TERMS = [
    'photocatalyst', 'baryon', 'graphene', 'nanoparticle', 'polymer', 
    'lattice', 'spectroscopy', 'quantum', 'magnetic', 'catalysis', 
    'solar cell', 'battery', 'fluid dynamics', 'semiconductor', 
    'crystallography', 'astrophysics', 'galaxy', 'telescope', 's-scheme'
]

# --- 2. STAFF DISCOVERY ---
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
        return sorted(list(names))
    except: return []

# --- 3. SMART SCORING (Stricter) ---
def get_smart_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code != 200: return None
        
        best_score = -100
        best_orcid = None
        
        for cand in r.json().get('results', []):
            score = 0
            # Metadata text
            affs = [a.get('institution', {}).get('display_name', '').lower() for a in cand.get('affiliations', [])]
            topics = [t.get('display_name', '').lower() for t in cand.get('topics', [])]
            full_text = " ".join(affs + topics)
            
            # POSITIVE
            if 'demography' in full_text: score += 20
            if 'sociology' in full_text: score += 15
            if 'population' in full_text: score += 15
            if 'economics' in full_text: score += 5
            if 'oxford' in full_text: score += 5
            
            # NEGATIVE (Expanded)
            if any(x in full_text for x in ['chemistry', 'materials', 'physics', 'engineering', 'energy', 'device', 'nano']):
                score -= 500 # Immediate disqualification

            if score > best_score and score > 10: # Threshold raised to 10
                best_score = score
                best_orcid = cand['orcid'].replace('https://orcid.org/', '')
                
        return best_orcid
    except: return None

# --- 4. FETCH & FILTER ---
def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2020-01-01&sort=created&order=desc&rows=40"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                title = item.get('title', ['Untitled'])[0]
                journal = item.get('container-title', [''])[0]
                
                # --- THE NUCLEAR FILTER ---
                # Check Title and Journal for forbidden engineering terms
                check_text = (title + " " + journal).lower()
                if any(bad in check_text for bad in BLACKLIST_TERMS):
                    continue # Skip this paper

                # Date Logic
                date_obj = item.get('created') or item.get('published-online')
                if date_obj and 'date-parts' in date_obj:
                    d = date_obj['date-parts'][0]
                    final_date = "{:04d}-{:02d}-{:02d}".format(*d) if len(d)==3 else "{:04d}-{:02d}-01".format(*d)
                else: final_date = datetime.now().strftime('%Y-%m-%d')

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'Paper Title': title,
                    'Journal Name': journal if journal else "Preprint",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': "Preprint" if (item.get('subtype')=='preprint') else "Journal Article",
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'].lower().strip()
                })
    except: pass
    return works

def process_author(name):
    orcid = get_smart_orcid(name)
    return fetch_works(name, orcid) if orcid else []

if __name__ == "__main__":
    staff = get_staff_list()
    all_recs = []
    # 8 Workers
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(process_author, n): n for n in staff}
        for f in as_completed(futures):
            if f.result(): all_recs.extend(f.result())

    if all_recs:
        df = pd.DataFrame(all_recs)
        df = df.sort_values(by='Date Available Online', ascending=False).drop_duplicates(subset=['DOI_Clean'])
        df.drop(columns=['DOI_Clean'], inplace=True)
        # Ensure cols
        for c in ['Date Available Online','LCDS Author','Paper Title','Journal Name','Citation Count','Publication Type','DOI']:
            if c not in df.columns: df[c] = ""
        
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records (Cleaned).")
    else:
        print("No records found.")
