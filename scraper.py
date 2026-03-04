import requests
import pandas as pd
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIG ---
HEADERS = {'User-Agent': 'LCDS-Tracker/Final (mailto:research_team@example.com)'}
ORCID_CSV_PATH = "data/lcds_people_orcid_updated.csv"
OUTPUT_CSV_PATH = "data/lcds_publications.csv"
START_DATE = "2019-09-01"

# --- 1. LOAD CSV ROSTER ---
def load_roster():
    roster = {}
    if os.path.exists(ORCID_CSV_PATH):
        try:
            df = pd.read_csv(ORCID_CSV_PATH)
            for _, row in df.iterrows():
                name = str(row.get('Name', '')).strip()
                if not name: continue
                
                status = str(row.get('Status', 'Not Found')).strip().lower()
                orcid = str(row.get('ORCID', '')).strip()
                if orcid == 'nan': orcid = None
                
                roster[name.lower()] = {'name': name, 'status': status, 'orcid': orcid}
            print(f"Loaded {len(roster)} entries from CSV.")
        except Exception as e: print(f"CSV Error: {e}")
    return roster

# --- 2. WEBSITE SCAN ---
def scan_website(roster):
    url = "https://www.demography.ox.ac.uk/people"
    print("Scanning website...")
    new_found = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        selectors = ['h3.paragraph-side-title', '.views-field-title a', '.person-name', 'h3.node__title']
        for s in selectors:
            for el in soup.select(s):
                raw = el.get_text(strip=True)
                clean = re.sub(r'^(Dr|Prof|Professor|Mr|Mrs|Ms|Mx)\.?\s+', '', raw, flags=re.IGNORECASE)
                clean = clean.split(' - ')[0].split(',')[0].strip()
                
                if any(x in clean for x in ["View profile", "Read more", "Contact"]): continue
                
                if 2 <= len(clean.split()) <= 5 and clean.lower() not in roster:
                    new_found.append({'name': clean, 'status': 'not found', 'orcid': None})
    except: pass
    return new_found

# --- 3. RESOLVE ORCID ---
def resolve_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for res in r.json().get('results', []):
                if 'orcid' not in res: continue
                affs = " ".join([a.get('institution', {}).get('display_name', '') for a in res.get('affiliations', [])]).lower()
                last = res.get('last_known_institution', {}).get('display_name', '').lower()
                if any(k in (affs + " " + last) for k in ['oxford', 'leverhulme', 'demographic', 'nuffield']):
                    return res['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 4. FETCH DATA ---
def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{START_DATE}&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                # Date
                d = item.get('created') or item.get('published-online') or item.get('published-print')
                date_str = datetime.now().strftime('%Y-%m-%d')
                if d and 'date-parts' in d:
                    p = d['date-parts'][0]
                    date_str = f"{p[0]}-{p[1]:02d}-{p[2]:02d}" if len(p)==3 else f"{p[0]}-01-01"
                elif d and 'date-time' in d:
                    date_str = str(d['date-time']).split('T')[0]

                w_type = "Preprint" if item.get('subtype')=='preprint' else "Journal Article"
                
                works.append({
                    'Date Available Online': date_str,
                    'LCDS Author': name,
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Journal Name': item.get('container-title', [''])[0] or "Preprint",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'],
                    'Year': date_str.split('-')[0]
                })
    except: pass
    return works

def enrich_citations(records):
    if not records: return []
    dois = [r['DOI_Clean'] for r in records]
    
    def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    
    cit_map = {}
    for chunk in chunker(dois, 50):
        try:
            f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            r = requests.get(f"https://api.openalex.org/works?filter={f}&select=doi,cited_by_count", headers=HEADERS)
            if r.status_code == 200:
                for res in r.json().get('results', []):
                    d = res.get('doi', '').replace('https://doi.org/', '')
                    cit_map[d] = res.get('cited_by_count', 0)
        except: pass

    for r in records:
        # Use OpenAlex citation count if available (usually higher), else keep Crossref
        if r['DOI_Clean'] in cit_map:
            r['Citation Count'] = max(r['Citation Count'], cit_map[r['DOI_Clean']])
        del r['DOI_Clean']
    return records

# --- WORKER ---
def process(p):
    name = p['name']
    if 'ignore' in p['status']: return []
    
    orcid = p['orcid']
    if not orcid and 'not found' in p['status']:
        orcid = resolve_orcid(name)
    
    if not orcid: return []
    
    raw = fetch_works(name, orcid)
    return enrich_citations(raw)

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    roster = load_roster()
    new_peeps = scan_website(roster)
    
    full_list = list(roster.values()) + new_peeps
    print(f"Processing {len(full_list)} people...")
    
    all_data = []
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(process, p): p['name'] for p in full_list}
        for f in as_completed(futures):
            if res := f.result(): all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data).sort_values('Date Available Online', ascending=False)
        df.drop_duplicates(subset=['DOI'], inplace=True)
        df.to_csv(OUTPUT_CSV_PATH, index=False)
        print(f"Saved {len(df)} records.")
    else:
        pd.DataFrame(columns=['Date Available Online']).to_csv(OUTPUT_CSV_PATH, index=False)
