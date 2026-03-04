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
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', 'div.person-name', 'span.field-content h3', '.views-field-title a']
        names = set()
        for s in selectors:
            for el in soup.select(s):
                n = el.get_text(strip=True)
                if n and len(n.split()) > 1: names.add(n)
        
        # Hardcoded additions
        names.add("Ursula Gazeley")
        names.add("Melinda Mills")
        return sorted(list(names))
    except Exception: 
        return ["Ursula Gazeley", "Melinda Mills"]

def standardize_date(d):
    """Aggressive date parser. Prefer YYYY-MM-DD."""
    if not d: return None
    try:
        # Handle Crossref date-parts [2024, 1, 15]
        if isinstance(d, list):
            p = d[0]
            if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
            if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
            if len(p) >= 1: return f"{p[0]}-01-01"
        # Handle ISO strings "2024-01-15T..."
        return str(d).split('T')[0]
    except: return None

def resolve_orcid(name):
    """Finds ORCID for a name using OpenAlex."""
    try:
        res = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for author in res.json().get('results', []):
                orcid = author.get('orcid')
                if not orcid: continue
                return orcid.replace('https://orcid.org/', '')
    except: pass
    return None

def fetch_hybrid_data(name, orcid):
    """Combines Wide-Net tags from your script with our enriched metadata."""
    papers = []
    
    # 1. CROSSREF (Primary Source for Recent Dates)
    try:
        # Sort by 'created' to get the absolute newest DOIs
        res = requests.get(f"https://api.crossref.org/works?filter=orcid:{orcid}&sort=created&order=desc", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for item in res.json().get('message', {}).get('items', []):
                # PRIORITY: 'published-online' -> 'created' -> 'published-print'
                date_source = item.get('published-online') or item.get('created') or item.get('published-print')
                
                # Careful date extraction
                final_date = None
                if date_source and 'date-parts' in date_source:
                    final_date = standardize_date(date_source['date-parts'])
                elif date_source and 'date-time' in date_source:
                     final_date = str(date_source['date-time']).split('T')[0]
                
                # Fallback to current year if totally missing
                if not final_date: final_date = datetime.now().strftime('%Y-%m-%d')

                papers.append({
                    'Date Available Online': final_date,
                    'LCDS Author': name,
                    'Paper Title': item.get('title', [''])[0],
                    'Journal Name': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint",
                    'DOI': f"https://doi.org/{item.get('DOI')}",
                    'Journal Area': "Pending (Recent)", # Placeholder
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'Publication Type': "Preprint" if item.get('subtype') == 'preprint' else "Journal Article",
                    'Source': 'Crossref'
                })
    except: pass

    # 2. OPENALEX (Enrichment & History)
    try:
        res = requests.get(f"https://api.openalex.org/works?filter=author.orcid:https://orcid.org/{orcid}", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for r in res.json().get('results', []):
                topic = "Multidisciplinary"
                if r.get('primary_topic'):
                    topic = r['primary_topic'].get('field', {}).get('display_name', 'Multidisciplinary')
                
                # Use created_date if available
                date_str = r.get('created_date', r.get('publication_date'))
                
                papers.append({
                    'Date Available Online': date_str,
                    'LCDS Author': name,
                    'Paper Title': r.get('display_name'),
                    'Journal Name': r.get('primary_location', {}).get('source', {}).get('display_name') or "Preprint",
                    'DOI': r.get('doi'),
                    'Journal Area': topic,
                    'Citation Count': r.get('cited_by_count', 0),
                    'Publication Type': "Preprint" if r.get('type') in ['preprint', 'posted-content'] else "Journal Article",
                    'Source': 'OpenAlex'
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
        
        # DEDUPLICATION LOGIC:
        # 1. Sort by Date (Newest) and Source (OpenAlex has better Topics)
        # We want: Recent Date + OpenAlex Topic.
        # This is hard to do in one pass, so we prioritize the *existence* of OpenAlex data for the Topic column.
        
        df['doi_clean'] = df['DOI'].str.lower().str.replace('https://doi.org/', '', regex=False).str.strip()
        
        # Split into OA and CR
        oa_df = df[df['Source'] == 'OpenAlex'].set_index('doi_clean')
        cr_df = df[df['Source'] == 'Crossref'].set_index('doi_clean')
        
        # Merge: Take Crossref Dates (newer) but OpenAlex Topics (richer)
        # If record is in both, use CR date and OA topic.
        
        final_records = []
        all_dois = set(df['doi_clean'])
        
        for doi in all_dois:
            oa_rec = oa_df.loc[doi] if doi in oa_df.index else None
            cr_rec = cr_df.loc[doi] if doi in cr_df.index else None
            
            # Handle duplicates in index (rare but happens)
            if isinstance(oa_rec, pd.DataFrame): oa_rec = oa_rec.iloc[0]
            if isinstance(cr_rec, pd.DataFrame): cr_rec = cr_rec.iloc[0]

            record = {}
            if cr_rec is not None:
                record = cr_rec.to_dict() # Start with Crossref (Better Dates)
                if oa_rec is not None:
                    record['Journal Area'] = oa_rec['Journal Area'] # Overwrite with OA Topic
            elif oa_rec is not None:
                record = oa_rec.to_dict() # Fallback to OA
            
            final_records.append(record)
            
        final_df = pd.DataFrame(final_records)
        final_df = final_df.sort_values('Date Available Online', ascending=False)
        
        final_df.to_csv("data/lcds_publications.csv", index=False)
        print(f"Saved {len(final_df)} records.")
