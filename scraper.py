import requests
import pandas as pd
import os
import re
import csv
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
HEADERS = {'User-Agent': 'LCDS-Tracker/Final (mailto:research_team@example.com)'}
ORCID_CSV_PATH = "data/lcds_people_orcid_updated.csv"
OUTPUT_CSV_PATH = "data/lcds_publications.csv"
START_DATE = "2019-09-01"

# --- 1. LOAD CSV ROSTER ---
def load_csv_roster():
    roster = {}
    if os.path.exists(ORCID_CSV_PATH):
        try:
            df = pd.read_csv(ORCID_CSV_PATH)
            # Normalize columns
            df.columns = [c.strip().title() for c in df.columns]
            
            for _, row in df.iterrows():
                name = row.get('Name', '')
                if pd.isna(name) or str(name).strip() == '': continue
                
                clean_name = name.strip()
                status = str(row.get('Status', 'Not Found')).strip().lower()
                orcid = str(row.get('Orcid', '')).strip()
                if orcid == 'nan': orcid = None

                roster[clean_name.lower()] = {
                    'original_name': clean_name,
                    'status': status,
                    'orcid': orcid
                }
            print(f"[{datetime.now().time()}] Loaded {len(roster)} people from CSV.")
        except Exception as e:
            print(f"[CRITICAL] CSV Error: {e}")
    return roster

# --- 2. WEBSITE SCAN (FALLBACK) ---
def scan_website(roster):
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Scanning website...")
    new_found = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        selectors = ['h3.paragraph-side-title', '.views-field-title a', '.person-name', 'h3.node__title']
        found_names = set()
        
        for s in selectors:
            for el in soup.select(s):
                raw = el.get_text(strip=True)
                clean = re.sub(r'^(Dr|Prof|Professor|Mr|Mrs|Ms|Mx)\.?\s+', '', raw, flags=re.IGNORECASE)
                clean = clean.split(' - ')[0].split(',')[0].strip()
                junk = ["View profile", "Read more", "Contact", "Email", "Research"]
                if any(x.lower() in clean.lower() for x in junk): continue
                
                if 2 <= len(clean.split()) <= 5:
                    found_names.add(clean)
        
        for name in found_names:
            if name.lower() not in roster:
                new_found.append({
                    'original_name': name,
                    'status': 'not found',
                    'orcid': None
                })
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
                
                # Date Logic
                d = item.get('created') or item.get('published-online') or item.get('published-print')
                date_str = datetime.now().strftime('%Y-%m-%d')
                if d and 'date-parts' in d:
                    p = d['date-parts'][0]
                    date_str = f"{p[0]}-{p[1]:02d}-{p[2]:02d}" if len(p)==3 else f"{p[0]}-01-01"
                elif d and 'date-time' in d:
                    date_str = str(d['date-time']).split('T')[0]

                w_type = "Preprint" if item.get('subtype')=='preprint' else "Journal Article"
                
                works.append({
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'].lower().strip(), # Used for merging
                    'Date Available Online': date_str,
                    'LCDS Author': name, # This will be aggregated later
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Journal Name': item.get('container-title', [''])[0] or "Preprint",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'Country': "Global",
                    'Journal Area': "Multidisciplinary",
                    'Year': date_str.split('-')[0]
                })
    except: pass
    return works

def enrich_meta(records):
    """Adds Topic and Country from OpenAlex"""
    if not records: return []
    dois = list(set(r['DOI_Clean'] for r in records))
    
    def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    
    meta_map = {}
    for chunk in chunker(dois, 40):
        try:
            f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,primary_topic,authorships"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for res in r.json().get('results', []):
                    d = res.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    
                    topic = res.get('primary_topic', {}).get('field', {}).get('display_name', 'Multidisciplinary')
                    
                    countries = set()
                    for auth in res.get('authorships', []):
                         for aff in auth.get('institutions', []):
                             if aff.get('country_code'): countries.add(aff['country_code'])
                    country_str = ", ".join(list(countries)[:3]) if countries else "Global"

                    meta_map[d] = {'topic': topic, 'country': country_str}
        except: pass

    for r in records:
        if r['DOI_Clean'] in meta_map:
            r['Journal Area'] = meta_map[r['DOI_Clean']]['topic']
            r['Country'] = meta_map[r['DOI_Clean']]['country']
        del r['DOI_Clean'] # No longer needed after enrichment
    return records

# --- WORKER ---
def process(p):
    name = p['original_name']
    if 'ignore' in p['status']: return []
    
    orcid = p['orcid']
    if not orcid and 'not found' in p['status']:
        orcid = resolve_orcid(name)
    
    if not orcid: return []
    
    raw = fetch_works(name, orcid)
    return enrich_meta(raw)

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    roster = load_csv_roster()
    new_peeps = scan_website(roster)
    
    full_list = list(roster.values()) + new_peeps
    print(f"Processing {len(full_list)} people...")
    
    all_data = []
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(process, p): p['original_name'] for p in full_list}
        for f in as_completed(futures):
            if res := f.result(): all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data)
        
        # --- THE FIX: MERGE AUTHORS BY DOI ---
        # 1. Sort by Date first (so latest metadata is top)
        df = df.sort_values(by='Date Available Online', ascending=False)
        
        # 2. Define how to combine rows with the same DOI
        aggregation_rules = {
            'Date Available Online': 'first',
            'LCDS Author': lambda x: ', '.join(sorted(set(x))), # Merges "Mills" and "Dowd" -> "Dowd, Mills"
            'Paper Title': 'first',
            'Journal Name': 'first',
            'Journal Area': 'first',
            'Publication Type': 'first',
            'Citation Count': 'max', # Take the highest citation count found
            'Country': 'first',
            'Year': 'first'
        }
        
        # 3. Group by DOI and Aggregate
        df = df.groupby('DOI', as_index=False).agg(aggregation_rules)
        
        # 4. Final Cleanup
        cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
                'Journal Area', 'Publication Type', 'Citation Count', 'Country', 'DOI', 'Year']
        for c in cols:
             if c not in df.columns: df[c] = ""
        df = df[cols]
        
        df.to_csv(OUTPUT_CSV_PATH, index=False)
        print(f"SUCCESS: Saved {len(df)} unique records.")
    else:
        print("WARNING: No records found.")
        pd.DataFrame(columns=['Date Available Online']).to_csv(OUTPUT_CSV_PATH, index=False)
