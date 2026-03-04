import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'OxfordSubUnitTracker/5.0 (mailto:{mailto})'}

def get_staff_list():
    """
    Scrapes the LCDS People page for ALL staff.
    Prioritizes the 'h3.paragraph-side-title' tag as requested.
    """
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching full staff list from website...")
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # --- WIDE NET SELECTORS ---
        selectors = [
            'h3.paragraph-side-title', 
            '.views-field-title a', 
            '.person-name',
            'h3.node__title',
            'span.field-content h3'
        ]
        
        for s in selectors:
            for el in soup.select(s):
                raw_name = el.get_text(strip=True)
                
                # --- CLEANING ---
                clean = raw_name.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
                junk_terms = ["View profile", "Read more", "Contact", "Email"]
                if any(x in clean for x in junk_terms):
                    continue
                
                if clean and len(clean.split()) >= 2 and len(clean) < 50:
                    names.add(clean)
        
        staff_list = sorted(list(names))
        print(f"[{datetime.now().time()}] Successfully found {len(staff_list)} people.")
        return staff_list

    except Exception as e:
        print(f"[ERROR] Failed to scrape staff: {e}")
        return []

def get_orcid(name):
    """Resolves name to ORCID via OpenAlex (Metadata only)."""
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results: return results[0]['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

def standardize_date(date_parts):
    """Converts Crossref [YYYY, MM, DD] to YYYY-MM-DD string."""
    try:
        if not date_parts or not isinstance(date_parts, list): return None
        p = date_parts[0]
        if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
        if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
        if len(p) == 1: return "{:04d}-01-01".format(*p)
    except: return None
    return None

def fetch_crossref_works(name, orcid):
    """
    PRIMARY FETCH: Gets everything from CrossRef directly.
    Prioritizes 'created' date to catch extremely recent items.
    """
    works = []
    if not orcid: return []

    try:
        # Sort by 'created' to get the absolute newest DOIs first
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2020-01-01&sort=created&order=desc&rows=50"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                # --- 1. STRICT TYPE DETECTION ---
                raw_type = item.get('type', '')
                subtype = item.get('subtype', '')
                
                if raw_type == 'posted-content' or subtype == 'preprint':
                    pub_type = "Preprint"
                else:
                    pub_type = "Journal Article"

                # --- 2. AGGRESSIVE DATE LOGIC ---
                # We check 'published-online' first, then 'created'.
                # 'created' is the timestamp the DOI was minted. It is NEVER empty for valid DOIs.
                date_obj = item.get('published-online') or item.get('created') or item.get('published-print')
                
                final_date = None
                
                # Case A: Standard Crossref Date Parts [2024, 1, 15]
                if date_obj and 'date-parts' in date_obj:
                    final_date = standardize_date(date_obj['date-parts'])
                
                # Case B: Timestamp string (often found in 'created')
                elif date_obj and 'date-time' in date_obj:
                    final_date = str(date_obj['date-time']).split('T')[0]

                # Fallback
                if not final_date:
                    final_date = datetime.now().strftime('%Y-%m-%d')

                # --- 3. METADATA ---
                title = item.get('title', ['Untitled'])[0]
                journal = item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other"
                
                # Formatting Authors
                auth_list = []
                for a in item.get('author', []):
                    auth_list.append(f"{a.get('given','')} {a.get('family','')}")
                all_authors = ", ".join(auth_list)

                works.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'All Authors': all_authors,
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'Paper Title': title,
                    'Journal Name': journal,
                    'Journal Area': "Pending", # OpenAlex will fill this later
                    'Year of Publication': final_date.split('-')[0],
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': pub_type,
                    'DOI_Clean': item['DOI'].lower().strip()
                })
    except Exception as e:
        print(f"[WARN] CrossRef failed for {name}: {e}")
        
    return works

def enrich_topics(records):
    """
    SECONDARY: Asks OpenAlex for Topics ONLY.
    DOES NOT overwrite dates or titles.
    """
    if not records: return []
    
    # Extract DOIs to query
    dois = [r['DOI_Clean'] for r in records]
    
    # Map DOI -> Topic
    doi_map = {}
    
    # Chunking requests (OpenAlex limits)
    def chunker(seq, size):
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))

    for chunk in chunker(dois, 40):
        try:
            # Build filter string
            doi_filter = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
            url = f"https://api.openalex.org/works?filter={doi_filter}&per-page=50&select=doi,primary_topic"
            
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('results', []):
                    d_key = item.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    topic = "Multidisciplinary"
                    if item.get('primary_topic'):
                        topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')
                    doi_map[d_key] = topic
        except: pass

    # Apply Topics to Records
    for r in records:
        if r['DOI_Clean'] in doi_map:
            r['Journal Area'] = doi_map[r['DOI_Clean']]
        else:
            r['Journal Area'] = "Multidisciplinary" 
            
    return records

def process_author(name):
    # 1. Get ORCID (Metadata Only)
    orcid = get_orcid(name)
    if not orcid: return []
    
    # 2. Get Skeleton from CrossRef (Fast, Recent, Accurate Types)
    records = fetch_crossref_works(name, orcid)
    
    # 3. Enrich with Topics (OpenAlex)
    enriched_records = enrich_topics(records)
    
    return enriched_records

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_records = []
    if staff:
        print(f"Scanning {len(staff)} authors (Crossref Priority Mode)...")
        with ThreadPoolExecutor(max_workers=8) as exc:
            futures = {exc.submit(process_author, n): n for n in staff}
            for f in as_completed(futures):
                try:
                    res = f.result()
                    if res: all_records.extend(res)
                except Exception as e:
                    print(f"[CRITICAL] Thread failed: {e}")
    
    if all_records:
        df = pd.DataFrame(all_records)
        
        # Deduplicate (Keep first entry if same DOI appears for multiple authors)
        df = df.sort_values(by='Date Available Online', ascending=False)
        df = df.drop_duplicates(subset=['DOI_Clean'], keep='first')
        
        # Cleanup
        df = df.drop(columns=['DOI_Clean'])
        
        # Ensure all columns exist for the App
        expected_cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 
                         'Paper Title', 'Journal Name', 'Journal Area', 
                         'Year of Publication', 'Citation Count', 'Publication Type']
        
        for c in expected_cols:
            if c not in df.columns: df[c] = ""
            
        df = df[expected_cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found.")
        pd.DataFrame(columns=['Date Available Online']).to_csv("data/lcds_publications.csv", index=False)
