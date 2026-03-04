import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Pubs-Tracker/4.0 (mailto:{mailto})'}

def get_staff_list():
    """Scrapes staff names using h3.paragraph-side-title."""
    print(f"[{datetime.now().time()}] Fetching staff list...")
    names = set()
    try:
        # Use a real browser user-agent to avoid blocking
        browser_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get("https://www.demography.ox.ac.uk/people", headers=browser_headers, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        for el in soup.select('h3.paragraph-side-title'):
            clean = el.get_text(strip=True).replace('Dr ', '').replace('Prof ', '').strip()
            if clean and len(clean.split()) >= 2: 
                names.add(clean)
        
        # Hardcoded Safety Net
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        return sorted(list(names))
    except Exception as e:
        print(f"[WARN] Staff scrape failed: {e}")
        return ["Ursula Gazeley", "Melinda Mills"]

def get_orcid(name):
    """Resolves a Name to an ORCID using OpenAlex (Metadata lookup)."""
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS)
        if r.status_code == 200:
            results = r.json().get('results', [])
            if results:
                return results[0]['orcid'].replace('https://orcid.org/', '')
    except:
        pass
    return None

def fetch_crossref_works(name, orcid):
    """PRIMARY FETCH: Gets all works directly from CrossRef (Real-time)."""
    works = []
    if not orcid: return []

    try:
        # Fetch everything from 2019 onwards
        # Sort by 'published' desc to get the absolute newest items first
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-01-01&sort=published&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=20)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                if 'DOI' not in item: continue
                
                # 1. ROBUST DATE PARSING (The "Latest" Fix)
                # Prioritize 'published-online' -> 'published-print' -> 'issued' -> 'created'
                date_source = item.get('published-online') or item.get('published-print') or item.get('issued')
                
                final_date = None
                if date_source and 'date-parts' in date_source:
                    parts = date_source['date-parts'][0]
                    if len(parts) == 3:
                        final_date = f"{parts[0]}-{parts[1]:02d}-{parts[2]:02d}"
                    elif len(parts) == 2:
                        final_date = f"{parts[0]}-{parts[1]:02d}-01"
                    else:
                        final_date = f"{parts[0]}-01-01"
                
                # Fallback: Use 'created' timestamp (When DOI was minted)
                if not final_date:
                    try:
                        created = item.get('created', {}).get('date-time', '')
                        final_date = created.split('T')[0]
                    except: 
                        final_date = datetime.now().strftime('%Y-%m-%d')

                # 2. Type Logic
                subtype = item.get('subtype', '')
                w_type = "Preprint" if subtype == 'preprint' or item.get('type') == 'posted-content' else "Journal Article"
                
                # 3. Build Skeleton Record
                works.append({
                    'DOI_Clean': item['DOI'].lower().strip(), # Helper for merging
                    'DOI': f"https://doi.org/{item['DOI']}",
                    'Paper Title': item.get('title', ['Untitled'])[0],
                    'Date Available Online': final_date,
                    'Year of Publication': final_date.split('-')[0],
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint/Other",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': w_type,
                    'LCDS Author': name,
                    'Journal Area': "Pending (Recent)", # Placeholder
                    'All Authors': ", ".join([f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])])
                })
    except Exception as e:
        print(f"[WARN] CrossRef failed for {name}: {e}")
        
    return works

def enrich_with_openalex(records):
    """SECONDARY FETCH: Adds 'Beef' (Topics) to the CrossRef Skeleton."""
    if not records: return []
    
    # Extract DOIs to query in bulk
    dois = [r['DOI_Clean'] for r in records]
    
    # OpenAlex allows filtering by DOI pipe-separated (limited to ~50 per call, so we chunk)
    def chunker(seq, size):
        return (seq[pos:pos + size] for pos in range(0, len(seq), size))

    doi_map = {} # Map DOI -> Topic
    
    for chunk in chunker(dois, 50):
        doi_filter = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
        try:
            url = f"https://api.openalex.org/works?filter={doi_filter}&per-page=50"
            r = requests.get(url, headers=HEADERS)
            if r.status_code == 200:
                for item in r.json().get('results', []):
                    d_key = item.get('doi', '').replace('https://doi.org/', '').lower().strip()
                    
                    # Extract Topic
                    topic = "Multidisciplinary"
                    if item.get('primary_topic'):
                        topic = item['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')
                    
                    doi_map[d_key] = topic
        except:
            pass

    # Merge Topic back into records
    for r in records:
        if r['DOI_Clean'] in doi_map:
            r['Journal Area'] = doi_map[r['DOI_Clean']]
            
    return records

def process_author(name):
    # 1. Get ORCID
    orcid = get_orcid(name)
    if not orcid: return []
    
    # 2. Get Skeleton from CrossRef (Fast & Fresh)
    skeleton = fetch_crossref_works(name, orcid)
    
    # 3. Add Beef from OpenAlex (Rich Metadata)
    full_cow = enrich_with_openalex(skeleton)
    
    return full_cow

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_records = []
    if staff:
        print(f"Scanning {len(staff)} authors (CrossRef First Strategy)...")
        with ThreadPoolExecutor(max_workers=5) as exc:
            futures = {exc.submit(process_author, n): n for n in staff}
            for f in as_completed(futures):
                try:
                    res = f.result()
                    if res: all_records.extend(res)
                except Exception as e:
                    print(f"[CRITICAL] Thread failed: {e}")
    
    # Save CSV
    if all_records:
        df = pd.DataFrame(all_records)
        
        # Deduplicate (If multiple authors are on the same paper, keep one)
        df = df.sort_values(by='Date Available Online', ascending=False)
        df = df.drop_duplicates(subset=['DOI_Clean'], keep='first')
        
        # Cleanup
        df = df.drop(columns=['DOI_Clean'])
        
        # Verify Columns
        cols = ['Date Available Online', 'LCDS Author', 'All Authors', 'DOI', 'Paper Title', 
                'Journal Name', 'Journal Area', 'Year of Publication', 'Citation Count', 'Publication Type']
        for c in cols:
            if c not in df.columns: df[c] = ""
            
        df = df[cols]
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"SUCCESS: Saved {len(df)} records.")
    else:
        print("WARNING: No records found. Creating empty CSV.")
        pd.DataFrame(columns=['Date Available Online']).to_csv("data/lcds_publications.csv", index=False)
