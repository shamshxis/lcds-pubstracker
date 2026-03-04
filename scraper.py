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
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list from {url}...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for el in soup.select('h3.paragraph-side-title'):
            raw_name = el.get_text(strip=True)
            clean_name = raw_name.replace('Dr ', '').replace('Prof ', '').strip()
            if clean_name and len(clean_name.split()) >= 2: 
                names.add(clean_name)
        
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        return sorted(list(names))
    except Exception as e:
        print(f"[ERROR] Staff scrape failed: {e}")
        return ["Ursula Gazeley", "Melinda Mills"]

def resolve_orcid(name):
    """Finds ORCID for a name using OpenAlex (needed for Crossref)."""
    try:
        url = "https://api.openalex.org/authors"
        r = requests.get(url, params={'search': name}, headers=HEADERS)
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results:
                # Returns '0000-0000-0000-0000'
                return results[0]['orcid'].replace('https://orcid.org/', '')
    except:
        pass
    return None

def fetch_openalex_data(name):
    """Main historical fetch with rich topics."""
    works = []
    try:
        url_author = "https://api.openalex.org/authors"
        r = requests.get(url_author, params={'search': name}, headers=HEADERS)
        if r.status_code != 200 or not r.json().get('results'): return []
        
        author_id = r.json()['results'][0]['id']
        
        url_works = "https://api.openalex.org/works"
        # Get everything from 2019 onwards
        filter_str = f"author.id:{author_id},publication_year:>2018"
        params = {'filter': filter_str, 'per-page': 200}
        
        rw = requests.get(url_works, params=params, headers=HEADERS)
        if rw.status_code == 200:
            for item in rw.json().get('results', []):
                
                # Determine Type
                w_type = "Journal Article"
                if item.get('type') in ['preprint', 'posted-content']:
                    w_type = "Preprint"
                
                # Get Field
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
    except Exception: pass
    return works

def fetch_recent_crossref(name, orcid):
    """Targeted Crossref fetch for just the last 6 months (Real-time catch)."""
    works = []
    if not orcid: return []
    
    try:
        # Filter: From 6 months ago to today
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{datetime.now().year-1}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            items = r.json().get('message', {}).get('items', [])
            for item in items:
                # Convert Crossref date parts to YYYY-MM-DD
                try:
                    date_parts = item['issued']['date-parts'][0]
                    pub_date = f"{date_parts[0]}-{date_parts[1]:02d}-{date_parts[2]:02d}"
                except:
                    pub_date = str(item.get('created', {}).get('date-parts', [[datetime.now().year]])[0][0])
                
                # Determine Type
                subtype = item.get('subtype', '')
                w_type = "Preprint" if subtype == 'preprint' or item.get('type') == 'posted-content' else "Journal Article"

                # Standardize DOI
                doi = f"https://doi.org/{item.get('DOI')}"
                
                works.append({
                    'Date Available Online': pub_date,
                    'LCDS Author': name,
                    'All Authors': ", ".join([f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]),
                    'DOI': doi,
                    'Paper Title': item.get('title', [''])[0],
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other",
                    'Journal Area': "Pending (Recent)", # Crossref doesn't have topics, OpenAlex will fill this later
                    'Year of Publication': date_parts[0],
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'Source': 'Crossref'
                })
    except Exception: pass
    return works

def process_author(name):
    """Worker function to do both fetches for one author."""
    # 1. OpenAlex (Bulk)
    data = fetch_openalex_data(name)
    
    # 2. Crossref (Recent Speed Boost)
    orcid = resolve_orcid(name)
    if orcid:
        recent_data = fetch_recent_crossref(name, orcid)
        data.extend(recent_data)
        
    return data

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_records = []
    if staff:
        print(f"Starting hybrid scrape for {len(staff)} staff...")
        with ThreadPoolExecutor(max_workers=5) as exc:
            futures = {exc.submit(process_author, n): n for n in staff}
            for f in as_completed(futures):
                all_records.extend(f.result())
    
    if all_records:
        df = pd.DataFrame(all_records)
        
        # --- DEDUPLICATION LOGIC ---
        # 1. Sort: OpenAlex first (better data), then recent dates
        # This ensures if we have duplicates, we keep the OpenAlex one with the "Journal Area"
        df['Source_Rank'] = df['Source'].apply(lambda x: 1 if x == 'OpenAlex' else 2)
        df = df.sort_values(by=['DOI', 'Source_Rank'])
        
        # 2. Drop duplicates by DOI, keeping the first (OpenAlex)
        df = df.drop_duplicates(subset=['DOI'], keep='first').drop(columns=['Source_Rank', 'Source'])
        
        # 3. Final Sort by Date (Newest first)
        df = df.sort_values(by='Date Available Online', ascending=False)
        
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"Saved {len(df)} records. Top 3 recent:")
        print(df[['Date Available Online', 'Paper Title', 'Source']].head(3))
    else:
        # Create empty with new columns
        cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 'Paper Title', 
                'Journal Name', 'Journal Area', 'Year of Publication', 'Citation Count', 'Publication Type']
        pd.DataFrame(columns=cols).to_csv("data/lcds_publications.csv", index=False)
