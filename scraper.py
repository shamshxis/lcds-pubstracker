import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Impact-Tracker/2.0 (mailto:{mailto})'}

# --- 1. DISCOVERY ---
def get_staff_list():
    """Scrapes LCDS website for staff names."""
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', '.views-field-title a', '.person-name', 'h3.node__title']
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').strip()
                if any(x in clean for x in ["View profile", "Read more", "Contact"]): continue
                if len(clean.split()) >= 2 and len(clean) < 40:
                    names.add(clean)
        names.add("Melinda Mills") # Ensure key lead is there
        return sorted(list(names))
    except: return ["Melinda Mills", "Ursula Gazeley"]

# --- 2. ORCID ---
def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results: return results[0]['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 3. FETCH (Your Logic) ---
def standardize_date(date_parts):
    try:
        if not date_parts: return None
        p = date_parts[0]
        if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
        if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
        return "{:04d}-01-01".format(*p)
    except: return None

def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-09-01&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            items = r.json().get('message', {}).get('items', [])
            for item in items:
                # Preprint detection
                is_pp = item.get('subtype') == 'preprint' or item.get('type') == 'posted-content'
                
                # Date logic
                d_obj = item.get('published-online') or item.get('created') or item.get('published-print')
                final_date = datetime.now().strftime('%Y-%m-%d')
                if d_obj and 'date-parts' in d_obj:
                    final_date = standardize_date(d_obj['date-parts'])
                elif d_obj and 'date-time' in d_obj:
                    final_date = str(d_obj['date-time']).split('T')[0]

                works.append({
                    'Date': final_date,
                    'Year': final_date.split('-')[0],
                    'LCDS Author': name,
                    'Title': item.get('title', ['Untitled'])[0],
                    'Journal': item.get('container-title', [''])[0] if item.get('container-title') else ("Preprint" if is_pp else "Unknown"),
                    'Type': "Preprint" if is_pp else "Journal Article",
                    'Citations': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{item.get('DOI')}",
                    'Field': 'Pending', # Placeholder
                    'Countries': ''     # Placeholder
                })
    except: pass
    return works

# --- 4. ENRICH (Safe Mode) ---
def safe_enrich(df):
    if df.empty: return df
    print(f"[{datetime.now().time()}] 🧠 Enriching data...")
    try:
        dois = df['DOI'].str.replace('https://doi.org/', '').tolist()
        doi_map = {}
        
        # Chunk requests
        def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
        
        for chunk in chunker(dois, 40):
            try:
                f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
                url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,primary_topic,authorships"
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    for res in r.json().get('results', []):
                        d = res.get('doi', '').replace('https://doi.org/', '').lower()
                        
                        # Topic
                        topic = "Multidisciplinary"
                        if res.get('primary_topic'): topic = res['primary_topic']['field']['display_name']
                        
                        # Countries
                        cntry = set()
                        for a in res.get('authorships', []):
                            for i in a.get('institutions', []):
                                if i.get('country_code'): cntry.add(i['country_code'])
                        
                        doi_map[d] = {'Field': topic, 'Countries': ",".join(cntry)}
            except: pass
            
        # Apply map
        for index, row in df.iterrows():
            d_key = row['DOI'].replace('https://doi.org/', '').lower()
            if d_key in doi_map:
                df.at[index, 'Field'] = doi_map[d_key]['Field']
                df.at[index, 'Countries'] = doi_map[d_key]['Countries']
                
    except Exception as e:
        print(f"Enrichment warning: {e}")
        
    return df

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_data = []
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(fetch_works, n, get_orcid(n)): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.sort_values('Date', ascending=False).drop_duplicates('DOI')
        
        # Save RAW data first (Safety)
        df.to_csv("data/lcds_publications.csv", index=False)
        
        # Try to Enrich
        df = safe_enrich(df)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"✅ SUCCESS: Saved {len(df)} records.")
    else:
        # Create empty CSV so App doesn't crash
        pd.DataFrame(columns=['Date','Year','LCDS Author','Title','Journal','Type','Citations','DOI','Field','Countries']).to_csv("data/lcds_publications.csv", index=False)
