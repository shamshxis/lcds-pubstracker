import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Pubs-Tracker/2.0 (mailto:{mailto})'}

def get_staff_list():
    """Scrapes staff names using h3.paragraph-side-title."""
    print(f"[{datetime.now().time()}] Fetching staff list...")
    names = set()
    try:
        res = requests.get("https://www.demography.ox.ac.uk/people", headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for el in soup.select('h3.paragraph-side-title'):
            raw = el.get_text(strip=True)
            clean = raw.replace('Dr ', '').replace('Prof ', '').strip()
            if clean and len(clean.split()) >= 2: 
                names.add(clean)
        
        # Safety Nets
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        return sorted(list(names))
    except Exception as e:
        print(f"[WARN] Staff scrape failed: {e}")
        return ["Ursula Gazeley", "Melinda Mills"]

def resolve_orcid(name):
    """Finds ORCID for a name using OpenAlex."""
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS)
        if r.status_code == 200:
            res = r.json().get('results', [])
            if res: return res[0]['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

def fetch_openalex_data(name):
    """Bulk historical fetch."""
    works = []
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS)
        if r.status_code != 200 or not r.json().get('results'): return []
        
        author_id = r.json()['results'][0]['id']
        filter_str = f"author.id:{author_id},publication_year:>2018"
        
        rw = requests.get("https://api.openalex.org/works", params={'filter': filter_str, 'per-page': 200}, headers=HEADERS)
        if rw.status_code == 200:
            for item in rw.json().get('results', []):
                # Type logic
                w_type = "Preprint" if item.get('type') in ['preprint', 'posted-content'] else "Journal Article"
                
                # Topic logic
                topic = "Multidisciplinary"
                if item.get('primary_topic'):
                    topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')

                works.append({
                    'Date Available Online': item.get('publication_date'),
                    'LCDS Author': name,
                    'All Authors': ", ".join([a['author']['display_name'] for a in item.get('authorships', [])]),
                    'DOI': item.get('doi'),
                    'Paper Title': item.get('display_name'),
                    'Journal Name': item.get('primary_location', {}).get('source', {}).get('display_name') or "Preprint/Other",
                    'Journal Area': topic,
                    'Year of Publication': item.get('publication_year'),
                    'Citation Count': item.get('cited_by_count', 0),
                    'Publication Type': w_type,
                    'Source': 'OpenAlex'
                })
    except Exception as e:
        print(f"[WARN] OpenAlex Error for {name}: {e}")
    return works

def fetch_recent_crossref(name, orcid):
    """Recent fetch (Last 1 year) to catch new items."""
    works = []
    if not orcid: return []
    
    try:
        # Fetch last 12 months
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{datetime.now().year-1}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                # --- FIX: ROBUST DATE PARSING ---
                try:
                    # Prefer 'published-online' (fastest), then 'published-print', then 'issued'
                    date_obj = item.get('published-online', item.get('published-print', item.get('issued', {})))
                    parts = date_obj['date-parts'][0]
                    
                    if len(parts) == 3:
                        pub_date = f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
                    elif len(parts) == 2:
                        pub_date = f"{parts[0]}-{parts[1]:02d}-01" # Default day 1
                    else:
                        pub_date = f"{parts[0]}-01-01" # Default Jan 1
                except:
                    pub_date = datetime.now().strftime('%Y-%m-%d')

                # Type logic
                subtype = item.get('subtype', '')
                w_type = "Preprint" if subtype == 'preprint' or item.get('type') == 'posted-content' else "Journal Article"

                # Title Cleanup
                title = item.get('title', [''])[0] if item.get('title') else "Untitled"

                works.append({
                    'Date Available Online': pub_date,
                    'LCDS Author': name,
                    'All Authors': ", ".join([f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]),
                    'DOI': f"https://doi.org/{item.get('DOI')}",
                    'Paper Title': title,
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other",
                    'Journal Area': "Pending (Recent)", 
                    'Year of Publication': parts[0] if 'parts' in locals() else datetime.now().year,
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'Source': 'Crossref'
                })
    except Exception as e:
        print(f"[WARN] Crossref Error for {name}: {e}")
    return works

def process_author(name):
    # Combined worker
    data = fetch_openalex_data(name)
    orcid = resolve_orcid(name)
    if orcid:
        data.extend(fetch_recent_crossref(name, orcid))
    return data

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_records = []
    if staff:
        print(f"Scanning {len(staff)} authors...")
        with ThreadPoolExecutor(max_workers=5) as exc:
            futures = {exc.submit(process_author, n): n for n in staff}
            for f in as_completed(futures):
                try:
                    all_records.extend(f.result())
                except Exception as e:
                    print(f"[CRITICAL] Thread failed: {e}")
    
    # ALWAYS create CSV
    if all_records:
        df = pd.DataFrame(all_records)
        
        # --- DEDUPLICATION STRATEGY ---
        # 1. OpenAlex is usually "better" (has Journal Area), but Crossref is "newer".
        # 2. Sort by Source (OpenAlex first) so we keep its metadata.
        df['Source_Rank'] = df['Source'].apply(lambda x: 1 if x == 'OpenAlex' else 2)
        df = df.sort_values(by=['DOI', 'Source_Rank'])
        
        # 3. Drop duplicates, keeping OpenAlex version if both exist
        df = df.drop_duplicates(subset=['DOI'], keep='first')
        
        # 4. Final Cleanup
        df = df.drop(columns=['Source_Rank', 'Source'])
        df = df.sort_values(by='Date Available Online', ascending=False)
        
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found. Creating empty CSV.")
        cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 'Paper Title', 
                'Journal Name', 'Journal Area', 'Year of Publication', 'Citation Count', 'Publication Type']
        pd.DataFrame(columns=cols).to_csv("data/lcds_publications.csv", index=False)
