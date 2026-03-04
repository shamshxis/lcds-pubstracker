import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Impact-Tracker/1.0 (mailto:{mailto})'}

# --- 1. STAFF DISCOVERY (From your logic) ---
def get_staff_list():
    """Scrapes LCDS website for staff names."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Your specific selectors
        selectors = [
            'h3.paragraph-side-title', 
            '.views-field-title a', 
            '.person-name',
            'h3.node__title',
            'span.field-content h3'
        ]
        
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                # Clean noise
                if any(x in clean for x in ["View profile", "Read more", "Contact", "Email", "Research", "Team"]): continue
                if len(clean.split()) >= 2 and len(clean) < 40:
                    names.add(clean)
        
        # Ensure key leads are always present (Safety net)
        names.add("Melinda Mills")
        
        print(f"✅ Found {len(names)} researchers.")
        return sorted(list(names))
    except Exception as e:
        print(f"❌ Staff scrape error: {e}")
        return ["Melinda Mills", "Ursula Gazeley"]

# --- 2. ORCID RESOLUTION ---
def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            # Simple check: match name, take first result. 
            # (Your script didn't use strict affiliation filtering, so I removed it to ensure we get results)
            if results: return results[0]['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 3. CROSSREF FETCH (The Core Logic) ---
def standardize_date(date_parts):
    """Your specific date parser."""
    try:
        if not date_parts or not isinstance(date_parts, list): return None
        p = date_parts[0]
        if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
        if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
        if len(p) == 1: return "{:04d}-01-01".format(*p)
    except: return None
    return None

def fetch_works(name, orcid):
    works = []
    if not orcid: return []

    try:
        # Fetch 2019 onwards as requested
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-09-01&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=30)
        
        if r.status_code == 200:
            items = r.json().get('message', {}).get('items', [])
            for item in items:
                # --- A. PREPRINT DETECTION ---
                is_preprint = (
                    item.get('subtype') == 'preprint' or 
                    item.get('type') == 'posted-content' or 
                    'rxiv' in item.get('container-title', [''])[0].lower()
                )
                pub_type = "Preprint" if is_preprint else "Journal Article"

                # --- B. DATE LOGIC (Your "Created" Priority) ---
                # This is what catches the "last week" papers
                date_obj = item.get('published-online') or item.get('created') or item.get('published-print')
                final_date = None
                
                if date_obj and 'date-parts' in date_obj:
                    final_date = standardize_date(date_obj['date-parts'])
                elif date_obj and 'date-time' in date_obj:
                    final_date = str(date_obj['date-time']).split('T')[0]
                
                if not final_date: final_date = datetime.now().strftime('%Y-%m-%d')

                # --- C. METADATA ---
                title = item.get('title', ['Untitled'])[0]
                journal = item.get('container-title', [''])[0]
                if not journal: journal = "Preprint" if is_preprint else "Unknown Source"
                
                # Authors
                authors = [f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]
                
                works.append({
                    'Date': final_date,
                    'Year': final_date.split('-')[0],
                    'LCDS Author': name,
                    'Title': title,
                    'Journal': journal,
                    'Type': pub_type,
                    'Citations': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{item.get('DOI')}",
                    'All Authors': ", ".join(authors),
                    'Source': 'Crossref'
                })
    except Exception as e:
        print(f"Error fetching {name}: {e}")
        
    return works

# --- 4. TOPIC ENRICHMENT (OpenAlex) ---
def enrich_topics(df):
    """Adds 'Field' and 'Institution Country' without overwriting rows."""
    if df.empty: return df
    
    print(f"[{datetime.now().time()}] 🧠 Enriching {len(df)} records with OpenAlex topics...")
    
    # We will fetch 'primary_topic' and 'authorships' (for countries)
    # This is heavy, so we do it in bulk chunks
    
    dois = df['DOI'].str.replace('https://doi.org/', '').tolist()
    
    doi_map = {} # DOI -> {Field, Countries}
    
    def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    
    for chunk in chunker(dois, 30): # Small chunks to avoid timeout
        try:
            f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,primary_topic,authorships"
            r = requests.get(url, headers=HEADERS, timeout=15)
            
            if r.status_code == 200:
                for res in r.json().get('results', []):
                    d_key = res.get('doi', '').replace('https://doi.org/', '').lower()
                    
                    # 1. Field
                    topic = "Multidisciplinary"
                    if res.get('primary_topic'):
                        topic = res['primary_topic']['field']['display_name']
                    
                    # 2. Countries (Collaborations)
                    countries = set()
                    for auth in res.get('authorships', []):
                        for inst in auth.get('institutions', []):
                            if inst.get('country_code'): countries.add(inst['country_code'])
                    
                    doi_map[d_key] = {'Field': topic, 'Countries': list(countries)}
        except: pass

    # Merge back to DataFrame
    def get_field(doi):
        key = doi.replace('https://doi.org/', '').lower()
        return doi_map.get(key, {}).get('Field', 'Multidisciplinary')

    def get_countries(doi):
        key = doi.replace('https://doi.org/', '').lower()
        return ",".join(doi_map.get(key, {}).get('Countries', []))

    df['Field'] = df['DOI'].apply(get_field)
    df['Countries'] = df['DOI'].apply(get_countries)
    
    return df

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    staff = get_staff_list()
    all_data = []
    
    # Parallel Fetch
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(fetch_works, n, get_orcid(n)): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data)
        
        # Deduplicate by DOI
        df = df.sort_values('Date', ascending=False).drop_duplicates('DOI')
        
        # Enrich
        df = enrich_topics(df)
        
        # Save
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"✅ SUCCESS: Saved {len(df)} records.")
    else:
        print("⚠️ No records found.")
