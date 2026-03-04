import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import re
import csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Hybrid (mailto:{mailto})'}
ORCID_CSV_PATH = "data/lcds_people_orcid_updated.csv"
START_DATE = "2019-09-01"  # Scrape from Sep 2019

# --- 1. LOAD CSV DATA ---
def load_csv_data():
    """
    Reads the CSV and returns a dictionary:
    { 'clean_name': {'orcid': '...', 'status': '...'} }
    """
    data_map = {}
    if os.path.exists(ORCID_CSV_PATH):
        try:
            df = pd.read_csv(ORCID_CSV_PATH)
            # Normalize names and store data
            for _, row in df.iterrows():
                if pd.notna(row['Name']):
                    clean_name = row['Name'].strip().lower()
                    status = str(row['Status']).strip().title() if pd.notna(row['Status']) else 'Not Found'
                    orcid = str(row['ORCID']).strip() if pd.notna(row['ORCID']) else None
                    
                    data_map[clean_name] = {
                        'orcid': orcid,
                        'status': status,
                        'original_name': row['Name'].strip()
                    }
            print(f"[{datetime.now().time()}] Loaded {len(data_map)} entries from CSV.")
        except Exception as e:
            print(f"[WARN] Could not load CSV: {e}")
    return data_map

# --- 2. WEBSITE SCRAPER (Fallback) ---
def get_website_names():
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Scraping website for new staff...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        selectors = ['h3.paragraph-side-title', '.views-field-title a', '.person-name', 'h3.node__title']
        for s in selectors:
            for el in soup.select(s):
                raw = el.get_text(strip=True)
                clean = re.sub(r'^(Dr|Prof|Professor|Mr|Mrs|Ms|Mx)\.?\s+', '', raw, flags=re.IGNORECASE)
                clean = clean.split(' - ')[0].split(',')[0].strip()
                
                junk = ["View profile", "Read more", "Contact", "Email", "Research"]
                if any(x.lower() in clean.lower() for x in junk): continue
                
                if 2 <= len(clean.split()) <= 5 and len(clean) < 50:
                    names.add(clean)
        return names
    except: return set()

# --- 3. ORCID RESOLVER (For 'Not Found' or New Names) ---
def resolve_orcid(name):
    """
    Finds ORCID via OpenAlex for names without one in CSV.
    Strictly checks for LCDS/Oxford affiliation.
    """
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for res in r.json().get('results', []):
                if 'orcid' not in res: continue
                
                # Check Affiliation History
                affs = [a.get('institution', {}).get('display_name', '').lower() for a in res.get('affiliations', [])]
                last = res.get('last_known_institution', {}).get('display_name', '').lower()
                full_text = " ".join(affs + [last])
                
                if any(k in full_text for k in ['oxford', 'leverhulme', 'demographic', 'nuffield', 'sociology']):
                    return res['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 4. FETCH CROSSREF (Primary Data) ---
def fetch_crossref(name, orcid):
    works = []
    if not orcid: return []
    
    try:
        # Fetch works from Sep 2019
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{START_DATE}&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue

                # Dates
                date_obj = item.get('created') or item.get('published-online') or item.get('published-print')
                final_date = datetime.now().strftime('%Y-%m-%d')
                if date_obj:
                    if 'date-time' in date_obj: final_date = str(date_obj['date-time']).split('T')[0]
                    elif 'date-parts' in date_obj:
                        p = date_obj['date-parts'][0]
                        final_date = f"{p[0]}-{p[1]:02d}-{p[2]:02d}" if len(p)==3 else f"{p[0]}-01-01"

                # Type
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
                    'Country': "Pending",  # Will fill via OpenAlex
                    'Journal Area': "Pending"
                })
    except: pass
    return works

# --- 5. ENRICH OPENALEX (Secondary Data) ---
def enrich_data(records):
    if not records: return []
    dois = [r['DOI_Clean'] for r in records]
    
    # Chunking requests
    def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    
    meta_map = {}
    
    for chunk in chunker(dois, 50):
        try:
            f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,primary_topic,authorships"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for res in r.json().get('results', []):
                    d = res.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    
                    # 1. Topic
                    topic = "Multidisciplinary"
                    if res.get('primary_topic'):
                        topic = res['primary_topic']['field']['display_name']
                    
                    # 2. Country (Extract from authorships)
                    countries = set()
                    for auth in res.get('authorships', []):
                         for aff in auth.get('institutions', []):
                             if aff.get('country_code'): countries.add(aff['country_code'])
                    country_str = ", ".join(list(countries)[:3]) if countries else "Global"

                    meta_map[d] = {'topic': topic, 'country': country_str}
        except: pass

    for r in records:
        meta = meta_map.get(r['DOI_Clean'], {})
        r['Journal Area'] = meta.get('topic', 'Multidisciplinary')
        r['Country'] = meta.get('country', 'Global')
        del r['DOI_Clean']
    return records

# --- WORKER ---
def process_author(name_entry):
    name, data = name_entry
    
    # Status Check
    if data['status'] == 'Ignore': return []
    
    orcid = data.get('orcid')
    
    # If no ORCID (Not Found / New Website Find), try to resolve it
    if not orcid or str(orcid) == 'nan':
        print(f"  [SEARCH] Resolving ORCID for {name}...")
        orcid = resolve_orcid(name)
    
    if not orcid: return []
    
    # Fetch & Enrich
    raw = fetch_crossref(data['original_name'], orcid)
    return enrich_data(raw)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. Load CSV
    csv_map = load_csv_data()
    
    # 2. Scrape Website & Merge
    web_names = get_website_names()
    final_list = []
    
    # Add CSV entries
    for clean_name, info in csv_map.items():
        final_list.append((clean_name, info))
        
    # Add NEW Website entries (if not in CSV)
    for w_name in web_names:
        clean_w = w_name.lower()
        if clean_w not in csv_map:
            final_list.append((clean_w, {
                'original_name': w_name,
                'status': 'Not Found', # Treat as unverified
                'orcid': None
            }))
            
    print(f"Processing {len(final_list)} authors...")
    
    all_recs = []
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(process_author, item): item[0] for item in final_list}
        for f in as_completed(futures):
            res = f.result()
            if res: all_recs.extend(res)
            
    if all_recs:
        df = pd.DataFrame(all_recs)
        df = df.sort_values(by='Date Available Online', ascending=False)
        df = df.drop_duplicates(subset=['DOI'], keep='first')
        
        cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
                'Journal Area', 'Publication Type', 'Citation Count', 'Country', 'DOI', 'Year']
        for c in cols:
             if c not in df.columns: df[c] = ""
        
        df = df[cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found.")
        pd.DataFrame(columns=['Date Available Online']).to_csv("data/lcds_publications.csv", index=False)
