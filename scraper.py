import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Final (mailto:{mailto})'}

# --- 1. IDENTIFY PEOPLE FROM WEBSITE ---
def get_staff_names():
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Scraping LCDS website...")
    names = set()
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Wide-net selectors to catch everyone
        selectors = ['h3.paragraph-side-title', '.views-field-title a', '.person-name', 'h3.node__title', 'span.field-content h3']
        for s in selectors:
            for el in soup.select(s):
                clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').strip()
                # Filter out junk
                if any(x in clean for x in ["View profile", "Read more", "Contact"]): continue
                
                if len(clean.split()) >= 2 and len(clean) < 50:
                    names.add(clean)
        
        return sorted(list(names))
    except Exception as e:
        print(f"[ERROR] Website scrape failed: {e}")
        return []

# --- 2. ORCID AFFILIATION MATCHING (The "Strict Filter") ---
def get_verified_orcid(name):
    """
    1. Search OpenAlex for the name.
    2. Check the ORCID record's 'affiliations' list.
    3. Return ORCID ONLY if they match Oxford/LCDS keywords.
    """
    try:
        # Search for author
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for result in results:
                if 'orcid' not in result: continue
                
                # DEEP DIVE: Check all historical affiliations, not just current
                affiliations = [a.get('institution', {}).get('display_name', '').lower() for a in result.get('affiliations', [])]
                last_known = result.get('last_known_institution', {}).get('display_name', '').lower()
                
                # Combine all institution text associated with this ORCID
                history_text = " ".join(affiliations + [last_known])
                
                # The "Green List" of keywords
                keywords = ['oxford', 'leverhulme', 'demographic', 'nuffield', 'sociology', 'population', 'lcds']
                
                # If ANY keyword appears in their ORCID history, they are valid.
                if any(k in history_text for k in keywords):
                    return result['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 3. CROSSREF FETCH (Primary Source) ---
def fetch_crossref(name, orcid):
    works = []
    if not orcid: return []
    
    try:
        # Fetch from 2019 to present (Crossref First)
        # Sort by 'created' to ensure we catch papers from "Last Week"
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-01-01&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue

                # A. DATE LOGIC (Priority: Created -> Online -> Print)
                date_obj = item.get('created') or item.get('published-online') or item.get('published-print')
                final_date = datetime.now().strftime('%Y-%m-%d') # Fallback
                
                if date_obj:
                    if 'date-time' in date_obj: # ISO format
                         final_date = str(date_obj['date-time']).split('T')[0]
                    elif 'date-parts' in date_obj: # Parts format
                        p = date_obj['date-parts'][0]
                        if len(p) == 3: final_date = f"{p[0]}-{p[1]:02d}-{p[2]:02d}"
                        elif len(p) == 2: final_date = f"{p[0]}-{p[1]:02d}-01"
                        elif len(p) == 1: final_date = f"{p[0]}-01-01"

                # B. TYPE LOGIC
                w_type = "Preprint" if item.get('subtype') == 'preprint' or item.get('type') == 'posted-content' else "Journal Article"

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
                    'Journal Area': "Pending" # Placeholder for OpenAlex
                })
    except: pass
    return works

# --- 4. OPENALEX ENRICHMENT (Secondary) ---
def enrich_data(records):
    if not records: return []
    
    # Map DOI -> Topic
    dois = [r['DOI_Clean'] for r in records]
    doi_map = {}
    
    # Bulk query OpenAlex for Topics (Chunked)
    def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
    
    for chunk in chunker(dois, 50):
        try:
            f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,primary_topic"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for res in r.json().get('results', []):
                    d = res.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    if res.get('primary_topic'):
                        doi_map[d] = res['primary_topic']['field']['display_name']
        except: pass

    # Apply only the Topic
    for r in records:
        r['Journal Area'] = doi_map.get(r['DOI_Clean'], "Multidisciplinary")
        del r['DOI_Clean'] # Cleanup
        
    return records

# --- WORKER ---
def process_author(name):
    # 1. Verify Affiliation via ORCID
    orcid = get_verified_orcid(name)
    if not orcid: return []
    
    # 2. Scrape Data
    raw_data = fetch_crossref(name, orcid)
    
    # 3. Enrich Data
    return enrich_data(raw_data)

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_names()
    print(f"Found {len(staff)} names. Starting verification & scrape...")
    
    all_data = []
    # Using 5 workers to be safe with rate limits
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(process_author, n): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.sort_values(by='Date Available Online', ascending=False)
        df = df.drop_duplicates(subset=['DOI'], keep='first') # Deduplicate
        
        # Ensure strict column order for UI
        cols = ['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
                'Journal Area', 'Publication Type', 'Citation Count', 'DOI', 'Year']
        
        # Fill missing cols if any
        for c in cols:
             if c not in df.columns: df[c] = ""

        df = df[cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} verified records.")
    else:
        print("WARNING: No records found.")
        # Create empty CSV with correct headers
        pd.DataFrame(columns=['Date Available Online', 'LCDS Author', 'Paper Title', 'Journal Name', 
                'Journal Area', 'Publication Type', 'Citation Count', 'DOI', 'Year']).to_csv("data/lcds_publications.csv", index=False)
