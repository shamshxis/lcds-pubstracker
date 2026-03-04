import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'OxfordSubUnitTracker/2.0 (mailto:{mailto})'}

def get_staff_list():
    """Captures names using the specific tags from your original script."""
    url = "https://www.demography.ox.ac.uk/people"
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        # Combined selectors from your original script
        selectors = ['h3.paragraph-side-title', 'div.person-name', 'span.field-content h3', '.views-field-title a']
        names = set()
        for s in selectors:
            for el in soup.select(s):
                n = el.get_text(strip=True)
                if n and len(n.split()) > 1: names.add(n)
        
        # Ensure comprehensive coverage without individual hardcoding
        staff_list = sorted(list(names))
        print(f"Found {len(staff_list)} staff members via web scraping.")
        return staff_list
    except Exception: 
        return []

def standardize_date(d):
    """Your original date standardization logic for max compatibility."""
    if not d: return None
    try:
        if isinstance(d, list):
            p = d[0]
            if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
            if len(p) >= 1: return f"{p[0]}-01-01"
        return str(d).split('T')[0]
    except: return None

def resolve_orcid(name):
    """Your original ORCID resolution logic to find Oxford-affiliated authors."""
    try:
        res = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for author in res.json().get('results', []):
                orcid = author.get('orcid')
                if not orcid: continue
                affs = [a.get('institution', {}).get('display_name', '').lower() for a in author.get('affiliations', [])]
                last = author.get('last_known_institution', {}).get('display_name', '').lower()
                all_inst_text = " ".join(affs + [last])
                # Tracking tags from your script
                targets = ['oxford', 'leverhulme', 'demographic science', 'nuffield', 'sociology', 'population', 'max planck', 'lcds']
                if any(t in all_inst_text for t in targets):
                    return orcid.replace('https://orcid.org/', '')
    except: pass
    return None

def fetch_hybrid_data(name, orcid):
    """Combines Wide-Net tags from your script with our enriched metadata."""
    papers = []
    # 1. OpenAlex: Using 'created_date' as 'available_online_date' from your script
    try:
        res = requests.get(f"https://api.openalex.org/works?filter=author.orcid:https://orcid.org/{orcid}", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for r in res.json().get('results', []):
                topic = "Multidisciplinary"
                if r.get('primary_topic'):
                    topic = r['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')
                
                papers.append({
                    'Date Available Online': standardize_date(r.get('created_date')), # Your original tag
                    'LCDS Author': name,
                    'All Authors': ", ".join([a['author']['display_name'] for a in r.get('authorships', [])]),
                    'DOI': r.get('doi'),
                    'Paper Title': r.get('display_name'),
                    'Journal Name': r.get('primary_location', {}).get('source', {}).get('display_name') or "Preprint",
                    'Journal Area': topic,
                    'Year of Publication': r.get('publication_year'),
                    'Citation Count': r.get('cited_by_count', 0),
                    'Publication Type': "Preprint" if r.get('type') in ['preprint', 'posted-content'] else "Journal Article"
                })
    except: pass

    # 2. Crossref: Using 'published-online' or 'created' from your script
    try:
        res = requests.get(f"https://api.crossref.org/works?filter=orcid:{orcid}&sort=published&order=desc", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for item in res.json().get('message', {}).get('items', []):
                od = item.get('published-online', {}).get('date-parts') or item.get('created', {}).get('date-parts')
                py = item.get('published', {}).get('date-parts', [[0]])[0][0]
                
                papers.append({
                    'Date Available Online': standardize_date(od), # Your original logic
                    'LCDS Author': name,
                    'All Authors': ", ".join([f"{a.get('given','')} {a.get('family','')}" for a in item.get('author', [])]),
                    'DOI': f"https://doi.org/{item.get('DOI')}" if 'DOI' in item else None,
                    'Paper Title': item.get('title', [''])[0],
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint",
                    'Journal Area': "Pending",
                    'Year of Publication': py if py != 0 else "Preprint",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': "Preprint" if item.get('type') == 'posted-content' else "Journal Article"
                })
    except: pass
    return papers

def process_person(n):
    o = resolve_orcid(n)
    return fetch_hybrid_data(n, o) if o else []

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    all_results = []

    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(process_person, n): n for n in staff}
        for f in as_completed(futures): all_results.extend(f.result())

    if all_results:
        df = pd.DataFrame(all_results)
        df = df.dropna(subset=['DOI'])
        df['doi_clean'] = df['DOI'].str.lower().str.replace('https://doi.org/', '', regex=False).str.strip()
        # Sort so we keep the OpenAlex version (with Journal Area) during deduplication
        df = df.sort_values('Journal Area', ascending=False).drop_duplicates(subset=['doi_clean']).drop(columns=['doi_clean'])
        df.to_csv("data/lcds_publications.csv", index=False)
