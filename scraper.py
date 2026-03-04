import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Genomics-Fertility-Safe/1.0 (mailto:{mailto})'}

# --- THE FIELD GUARD ---
# MUST NOT contain these (Physical Sciences)
PHYSICAL_SCIENCE_BLOCK = ['photocatalyst', 's-scheme', 'baryon', 'graphene', 'lattice', 'catalysis', 'quantum']

# MUST contain at least one of these to bypass generic blocks
SOCIAL_LIFE_ALLOW = ['genomic', 'fertility', 'reproduction', 'birth', 'mortality', 'health', 'population', 'sociology', 'demograph']

def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', '.views-field-title a']
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').strip()
                if clean and 2 <= len(clean.split()) < 5:
                    names.add(clean)
        return sorted(list(names))
    except: return []

def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            for cand in r.json().get('results', []):
                # Ensure they are at Oxford/LCDS/Leverhulme
                affs = " ".join([a.get('institution', {}).get('display_name', '').lower() for a in cand.get('affiliations', [])])
                topics = " ".join([t.get('display_name', '').lower() for t in cand.get('topics', [])])
                evidence = f"{affs} {topics}"
                
                # Check for LCDS-friendly keywords
                if any(x in evidence for x in ['oxford', 'leverhulme', 'lcds', 'demograph', 'sociology']):
                    oid = cand.get('orcid')
                    if oid: return oid.replace('https://orcid.org/', '')
    except: pass
    return None

def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        # Fetching 2024-2027 primarily for recent data
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2023-01-01&sort=created&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                title = item.get('title', ['Untitled'])[0].lower()
                journal = item.get('container-title', [''])[0].lower()
                
                # --- THE SMART FILTER ---
                # 1. If it's explicitly engineering/physics, bin it.
                if any(bad in title or bad in journal for bad in PHYSICAL_SCIENCE_BLOCK):
                    continue
                
                # 2. If it's not clearly engineering, but we want to be sure it's "our" Yan Liu,
                # we look for the LCDS/Genomics/Social signature.
                is_valid = any(good in title or good in journal for good in SOCIAL_LIFE_ALLOW)
                
                # If it doesn't have our keywords, but also isn't "banned" science, 
                # we keep it only if the journal isn't a hard-science journal.
                hard_science_journals = ['advanced materials', 'small', 'chem', 'physical review']
                if not is_valid and any(j in journal for j in hard_science_journals):
                    continue

                date_obj = item.get('created') or item.get('published-online')
                d = date_obj.get('date-parts', [[2025,1,1]])[0]
                final_date = "{:04d}-{:02d}-{:02d}".format(*d) if len(d)==3 else "{:04d}-{:02d}-01".format(*d)

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Journal Name': item.get('container-title', ['Preprint'])[0],
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': "Preprint" if (item.get('subtype')=='preprint') else "Journal Article",
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'].lower().strip()
                })
    except: pass
    return works

if __name__ == "__main__":
    staff = get_staff_list()
    all_recs = []
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(lambda n: fetch_works(n, get_orcid(n)), name): name for name in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_recs.extend(res)
    
    if all_recs:
        df = pd.DataFrame(all_recs).sort_values('Date Available Online', ascending=False)
        df.drop_duplicates('DOI_Clean', inplace=True)
        os.makedirs("data", exist_ok=True)
        df.drop(columns=['DOI_Clean']).to_csv("data/lcds_publications.csv", index=False)
