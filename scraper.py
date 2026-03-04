import requests
import pandas as pd
import os
import re
import csv
from datetime import datetime
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Final (mailto:{mailto})'}
# Pointing to your specific uploaded file
ORCID_CSV_PATH = "data/lcds_people_orcid_updated.csv"
OUTPUT_CSV_PATH = "data/lcds_publications.csv"
START_DATE = "2019-09-01"

# --- 1. LOAD & PARSE CSV ---
def load_csv_roster():
    """
    Parses the control CSV.
    Returns a dict: { 'clean_name': {'orcid': '...', 'status': '...'} }
    """
    roster = {}
    if os.path.exists(ORCID_CSV_PATH):
        try:
            df = pd.read_csv(ORCID_CSV_PATH)
            # Standardize columns
            df.columns = [c.strip().title() for c in df.columns]
            
            for _, row in df.iterrows():
                name = row.get('Name', '')
                if pd.isna(name) or str(name).strip() == '': continue
                
                clean_name = name.strip().lower()
                status = str(row.get('Status', 'Not Found')).strip().lower()
                orcid = str(row.get('Orcid', '')).strip()
                
                if orcid == 'nan': orcid = None

                roster[clean_name] = {
                    'original_name': name.strip(),
                    'status': status, # verified, ignore, not found
                    'orcid': orcid
                }
            print(f"[{datetime.now().time()}] Loaded {len(roster)} people from CSV.")
        except Exception as e:
            print(f"[CRITICAL] Failed to load CSV: {e}")
    else:
        print(f"[WARNING] CSV file not found at {ORCID_CSV_PATH}")
    return roster

# --- 2. WEBSITE DISCOVERY (FALLBACK) ---
def scan_website_for_new_people(existing_roster):
    """Scrapes website for names NOT in the CSV."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Scanning website for new additions...")
    new_finds = []
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        selectors = ['h3.paragraph-side-title', '.views-field-title a', '.person-name', 'h3.node__title']
        found_names = set()
        
        for s in selectors:
            for el in soup.select(s):
                raw = el.get_text(strip=True)
                # Cleanup
                clean = re.sub(r'^(Dr|Prof|Professor|Mr|Mrs|Ms|Mx)\.?\s+', '', raw, flags=re.IGNORECASE)
                clean = clean.split(' - ')[0].split(',')[0].strip()
                
                junk = ["View profile", "Read more", "Contact", "Email", "Research"]
                if any(x.lower() in clean.lower() for x in junk): continue
                
                if 2 <= len(clean.split()) <= 5 and len(clean) < 50:
                    found_names.add(clean)
        
        # Check against roster
        for name in found_names:
            if name.lower() not in existing_roster:
                new_finds.append({
                    'original_name': name,
                    'status': 'not found', # Treat as unverified
                    'orcid': None
                })
                
    except Exception as e:
        print(f"[ERROR] Website scan failed: {e}")
        
    return new_finds

# --- 3. ORCID RESOLVER (FOR 'NOT FOUND' STATUS) ---
def resolve_missing_orcid(name):
    """Attempts to find an Oxford/LCDS affiliated ORCID for unknown names."""
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for res in r.json().get('results', []):
                if 'orcid' not in res: continue
                
                # Affiliation Check
                affs = [a.get('institution', {}).get('display_name', '').lower() for a in res.get('affiliations', [])]
                last = res.get('last_known_institution', {}).get('display_name', '').lower()
                full_text = " ".join(affs + [last])
                
                if any(k in full_text for k in ['oxford', 'leverhulme', 'demographic', 'nuffield', 'sociology']):
                    return res['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 4. DATA FETCHING (CROSSREF + OPENALEX) ---
def fetch_publications(name, orcid):
    works = []
    if not orcid: return []
    
    try:
        # Crossref (Primary - Updated)
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{START_DATE}&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue

                # Date Logic
                date_obj = item.get('created') or item.get('published-online') or item.get('published-print')
                final_date = datetime.now().strftime('%Y-%m-%d')
                if date_obj:
                    if 'date-time' in date_obj: final_date = str(date_obj['date-time']).split('T')[0]
                    elif 'date-parts' in date_obj:
                        p = date_obj['date-parts'][0]
                        final_date = f"{p[0]}-{p[1]:02d}-{p[2]:02d}" if len(p)==3 else f"{p[0]}-01-01"

                w_type = "Preprint" if item.get('subtype')=='preprint' or item.get('type')=='posted-content' else "Journal Article"

                works.append({
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'DOI_Clean': item['DOI'].lower().strip(),
                    'Date Available Online': final_date,
                    'Year': final_date.split('-')[0],
                    'LCDS Author': name,
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'Country': "Global", # Placeholder
                    'Journal Area': "Multidisciplinary" # Placeholder
                })
    except: pass
    return works

def enrich_with_openalex(records):
    """Batch updates records with Topic and Country from OpenAlex."""
    if not records: return []
    dois = [r['DOI_Clean'] for r in records]
    
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
                    
                    # Topic
                    topic = res.get('primary_topic', {}).get('field', {}).get('display_name', 'Multidisciplinary')
                    
                    # Country
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
        del r['DOI_Clean']
    return records

# --- WORKER ---
def process_person(person_data):
    name = person_data['original_name']
    status = person_data['status']
    orcid = person_data['orcid']
    
    # 1. CHECK STATUS
    if 'ignore' in status:
        return []
    
    # 2. RESOLVE ORCID IF MISSING (BUT NOT IGNORED)
    if not orcid and 'not found' in status:
        print(f"  [SEARCH] Resolving ORCID for {name}...")
        orcid = resolve_missing_orcid(name)
        
    if not orcid: return []
    
    # 3. FETCH & ENRICH
    raw_data = fetch_publications(name, orcid)
    return enrich_with_openalex(raw_data)

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. Load Control File
    roster = load_csv_roster()
    
    # 2. Check Website for New People
    new_people = scan_website_for_new_people(roster)
    
    # 3. Combine Lists
    processing_list = list(roster.values()) + new_people
    print(f"Processing {len(processing_list)} individuals...")
    
    all_records = []
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(process_person, p): p['original_name'] for p in processing_list}
        for f in as_completed(futures):
            res = f.result()
            if res: all_records.extend(res)
            
    # 4. Save
    if all_records:
        df = pd.DataFrame(all_records)
        df = df.sort_values(by='Date Available Online', ascending=False)
        df = df.drop_duplicates(subset=['DOI'], keep='first')
        
        # Enforce Column Order
        cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
                'Journal Area', 'Publication Type', 'Citation Count', 'Country', 'DOI', 'Year']
        for c in cols:
             if c not in df.columns: df[c] = ""
        df = df[cols]
        
        df.to_csv(OUTPUT_CSV_PATH, index=False)
        print(f"SUCCESS: Saved {len(df)} records to {OUTPUT_CSV_PATH}")
    else:
        print("WARNING: No records found.")
        pd.DataFrame(columns=['Date Available Online']).to_csv(OUTPUT_CSV_PATH, index=False)
