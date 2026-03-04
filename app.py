import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Balanced/1.0 (mailto:{mailto})'}

# --- THE TRASH CAN ---
# If a paper title contains these, it is DELETED.
PAPER_BLACKLIST = [
    'photocatalyst', 's-scheme', 'baryon', 'graphene', 'lattice', 'perovskite', 
    'nanoparticle', 'catalysis', 'solar cell', 'quantum', 'spectroscopy'
]

def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', '.views-field-title a']
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                if clean and 2 <= len(clean.split()) < 5:
                    names.add(clean)
        return sorted(list(names))
    except: return []

def get_verified_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code != 200: return None
        for cand in r.json().get('results', []):
            affs = " ".join([a.get('institution', {}).get('display_name', '').lower() for a in cand.get('affiliations', [])])
            topics = " ".join([t.get('display_name', '').lower() for t in cand.get('topics', [])])
            evidence = f"{affs} {topics}"
            
            # BLOCK CHEMISTS
            if any(x in evidence for x in ['chemistry', 'physics', 'materials', 'engineering']):
                continue
            
            # REQUIRE SOCIAL SCIENCE / LCDS
            good_flags = ['leverhulme', 'lcds', 'demographic', 'demography', 'sociology', 'population', 'nuffield']
            if any(good in evidence for good in good_flags):
                oid = cand.get('orcid')
                return oid.replace('https://orcid.org/', '') if oid else None
        return None
    except: return None

def fetch_works(name, orcid):
    works = []
    try:
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2020-01-01&sort=created&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                title = item.get('title', ['Untitled'])[0]
                if any(bad in title.lower() for bad in PAPER_BLACKLIST): continue
                
                date_obj = item.get('created') or item.get('published-online')
                d = date_obj.get('date-parts', [[2024,1,1]])[0]
                final_date = "{:04d}-{:02d}-{:02d}".format(*d) if len(d)==3 else "{:04d}-{:02d}-01".format(*d)

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'Paper Title': title,
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
        futures = {exc.submit(lambda n: fetch_works(n, get_verified_orcid(n)), name): name for name in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_recs.extend(res)
    if all_recs:
        df = pd.DataFrame(all_recs).sort_values('Date Available Online', ascending=False).drop_duplicates('DOI_Clean')
        os.makedirs("data", exist_ok=True)
        df.drop(columns=['DOI_Clean']).to_csv("data/lcds_publications.csv", index=False)
