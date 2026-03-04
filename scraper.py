import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION (Directly from Colab) ---
HEADERS = {'User-Agent': 'LCDS-Impact-Tracker/2.0 (mailto:research@demography.ox.ac.uk)'}
TARGET_KEYWORDS = ['leverhulme', 'lcds', 'demographic science', 'nuffield', 'sociology', 'population']

def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', 'div.person-name', '.views-field-title a']
        names = list(set([el.get_text(strip=True) for s in selectors for el in soup.select(s) if len(el.get_text().split()) > 1]))
        if "Ursula Gazeley" not in names: names.append("Ursula Gazeley")
        return sorted(names)
    except: return ["Ursula Gazeley"]

def resolve_verified_orcid(name):
    """Only returns an ORCID if the profile matches LCDS/Demography keywords."""
    try:
        res = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for author in res.json().get('results', []):
                orcid = author.get('orcid')
                if not orcid: continue
                affs = " ".join([a.get('institution', {}).get('display_name', '').lower() for a in author.get('affiliations', [])])
                last = author.get('last_known_institution', {}).get('display_name', '').lower()
                topics = " ".join([t.get('display_name', '').lower() for t in author.get('topics', [])])
                metadata = affs + last + topics
                # Verification: Must be Oxford AND match an LCDS keyword
                if 'oxford' in metadata and any(sig in metadata for sig in TARGET_KEYWORDS):
                    return orcid.replace('https://orcid.org/', '')
    except: pass
    return None

def fetch_lcds_papers(name):
    orcid = resolve_verified_orcid(name)
    if not orcid: return []
    papers = []
    try:
        res = requests.get(f"https://api.openalex.org/works?filter=author.orcid:https://orcid.org/{orcid}", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for r in res.json().get('results', []):
                papers.append({
                    'LCDS Author': name,
                    'Paper Title': r.get('display_name'),
                    'Journal Name': r.get('host_venue', {}).get('display_name') or "Preprint/Other",
                    'Publication Type': "Preprint" if r.get('type') == 'posted-content' else "Journal Article",
                    'Citation Count': r.get('cited_by_count', 0),
                    'DOI': r.get('doi'),
                    'Year': r.get('publication_year'),
                    'Date Available Online': r.get('created_date')
                })
    except: pass
    return papers

if __name__ == "__main__":
    staff = get_staff_list()
    results = []
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(fetch_lcds_papers, n): n for n in staff}
        for f in as_completed(futures): results.extend(f.result())
    
    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['DOI'])
        # Colab Filter: Focus on 2024-2027 and Preprints
        df['year_str'] = df['Year'].astype(str)
        df = df[(df['year_str'].isin(['2024', '2025', '2026', '2027', 'Preprint'])) | (df['Publication Type'] == 'Preprint')]
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/lcds_publications.csv", index=False)
