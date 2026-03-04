import requests
import pandas as pd
import os
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
HEADERS = {'User-Agent': 'LCDS-Tracker/Final (mailto:research_team@example.com)'}
ORCID_CSV_PATH = "data/lcds_people_orcid_updated.csv"
OUTPUT_CSV_PATH = "data/lcds_publications.csv"
START_DATE = "2019-09-01"

# --- HELPER: NORMALIZE TITLE ---
def normalize_title(title):
    if not isinstance(title, str): return ""
    return re.sub(r'\W+', '', title).lower()

# --- 1. LOAD CSV ROSTER ---
def load_csv_roster():
    roster = {}
    if os.path.exists(ORCID_CSV_PATH):
        try:
            df = pd.read_csv(ORCID_CSV_PATH)
            # Normalize headers
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
        except Exception as e: print(f"CSV Error: {e}")
    else: print("CSV file not found.")
    return roster

# --- 2. WEBSITE SCAN ---
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
                if 2 <= len(clean.split()) <= 5: found_names.add(clean)
        
        for name in found_names:
            if name.lower() not in roster:
                new_found.append({'original_name': name, 'status': 'not found', 'orcid': None})
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
                
                d = item.get('created') or item.get('published-online') or item.get('published-print')
                date_str = datetime.now().strftime('%Y-%m-%d')
                if d and 'date-parts' in d:
                    p = d['date-parts'][0]
                    date_str = f"{p[0]}-{p[1]:02d}-{p[2]:02d}" if len(p)==3 else f"{p[0]}-01-01"
                elif d and 'date-time' in d: date_str = str(d['date-time']).split('T')[0]

                w_type = "Preprint" if item.get('subtype')=='preprint' else "Journal Article"
                
                works.append({
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'].lower().strip(),
                    'Date Available Online': date_str,
                    'LCDS Author': name,
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Journal Name': item.get('container-title', [''])[0] or "Preprint",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'Country': "Global",
                    'Year': date_str.split('-')[0]
                })
    except: pass
    return works

def enrich_meta(records):
    """Adds Country from OpenAlex"""
    if not records: return []
    dois = list(set(r['DOI_Clean'] for r in records))
    
    def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    
    meta_map = {}
    for chunk in chunker(dois, 40):
        try:
            f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,authorships"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for res in r.json().get('results', []):
                    d = res.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    countries = set()
                    for auth in res.get('authorships', []):
                         for aff in auth.get('institutions', []):
                             if aff.get('country_code'): countries.add(aff['country_code'])
                    meta_map[d] = ", ".join(list(countries)[:3]) if countries else "Global"
        except: pass

    for r in records:
        if r['DOI_Clean'] in meta_map: r['Country'] = meta_map[r['DOI_Clean']]
        del r['DOI_Clean'] 
    return records

# --- WORKER ---
def process(p):
    name = p['original_name']
    if 'ignore' in p['status']: return []
    
    orcid = p['orcid']
    if not orcid and 'not found' in p['status']: orcid = resolve_orcid(name)
    
    if not orcid: return []
    
    raw = fetch_works(name, orcid)
    return enrich_meta(raw)

# --- INTELLIGENT MERGE LOGIC ---
def apply_intelligent_merges(df):
    # 1. Merge by DOI
    df = df.sort_values(by='Date Available Online', ascending=False)
    df = df.groupby('DOI', as_index=False).agg({
        'Date Available Online': 'first',
        'LCDS Author': lambda x: ', '.join(sorted(set(x))), 
        'Paper Title': 'first',
        'Journal Name': 'first',
        'Publication Type': 'first',
        'Citation Count': 'max',
        'Country': 'first',
        'Year': 'first'
    })

    # 2. Normalize Title
    df['norm_title'] = df['Paper Title'].apply(normalize_title)
    
    # 3. Detect Transition (Preprint + Journal)
    ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    def resolve_group(group):
        if len(group) == 1: return group
        
        types = group['Publication Type'].str.lower().tolist()
        has_preprint = any('preprint' in t for t in types)
        has_journal = any('journal' in t for t in types)
        
        if has_preprint and has_journal:
            # Prefer Journal Article
            journal_row = group[group['Publication Type'].str.lower().str.contains('journal')].iloc[0].copy()
            
            # Add Notification if Recent
            pub_date = str(journal_row['Date Available Online'])
            if pub_date >= ninety_days_ago:
                journal_row['Paper Title'] = f"{journal_row['Paper Title']} (Journal Publication Now Available)"
            
            return pd.DataFrame([journal_row])
            
        return group.iloc[[0]]

    df = df.groupby('norm_title', group_keys=False).apply(resolve_group)
    if 'norm_title' in df.columns: df = df.drop(columns=['norm_title'])
    
    return df

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
        df = apply_intelligent_merges(df)
        
        cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
                'Publication Type', 'Citation Count', 'Country', 'DOI', 'Year']
        df = df[cols]
        df.to_csv(OUTPUT_CSV_PATH, index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        pd.DataFrame(columns=['Date Available Online']).to_csv(OUTPUT_CSV_PATH, index=False)
