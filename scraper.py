import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
# Matches your Colab setup exactly
HEADERS = {'User-Agent': 'OxfordSubUnitTracker/1.6 (mailto:your-email@example.com)'}
TARGET_INSTITUTIONS = ['oxford', 'leverhulme', 'demographic science', 'nuffield', 'sociology', 'population', 'max planck', 'lcds']

def get_staff_list():
    url = "https://www.demography.ox.ac.uk/people"
    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(res.text, 'html.parser')
        selectors = ['h3.paragraph-side-title', 'div.person-name', 'span.field-content h3', '.views-field-title a']
        names = []
        for s in selectors:
            for el in soup.select(s):
                n = el.get_text(strip=True)
                if n and len(n.split()) > 1: names.append(n)
        names = list(set(names))
        if "Ursula Gazeley" not in names: names.append("Ursula Gazeley")
        return sorted(names)
    except: return ["Ursula Gazeley"]

def resolve_orcid(name):
    try:
        res = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for author in res.json().get('results', []):
                orcid = author.get('orcid')
                if not orcid: continue
                affs = [a.get('institution', {}).get('display_name', '').lower() for a in author.get('affiliations', [])]
                last = author.get('last_known_institution', {}).get('display_name', '').lower()
                all_inst_text = " ".join(affs + [last])
                if any(t in all_inst_text for t in TARGET_INSTITUTIONS) or "Gazeley" in name:
                    return orcid.replace('https://orcid.org/', '')
    except: pass
    return None

def standardize_date(d):
    if not d: return "N/A"
    try:
        if isinstance(d, list):
            p = d[0]
            return "{:04d}-{:02d}-{:02d}".format(*p) if len(p) == 3 else str(p[0])
        return d.split('T')[0]
    except: return "N/A"

def fetch_papers(name):
    orcid = resolve_orcid(name)
    if not orcid: return []
    papers = []
    # OpenAlex
    try:
        res = requests.get(f"https://api.openalex.org/works?filter=author.orcid:https://orcid.org/{orcid}", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for r in res.json().get('results', []):
                papers.append({
                    'Date Available Online': standardize_date(r.get('created_date')),
                    'LCDS Author': name,
                    'Paper Title': r.get('display_name'),
                    'Journal Name': r.get('host_venue', {}).get('display_name') or "Preprint/Other",
                    'Publication Type': "Preprint" if r.get('type') == 'posted-content' else "Journal Article",
                    'Citation Count': r.get('cited_by_count', 0),
                    'DOI': r.get('doi'),
                    'Year': r.get('publication_year')
                })
    except: pass
    # Crossref
    try:
        res = requests.get(f"https://api.crossref.org/works?filter=orcid:{orcid}&sort=published&order=desc", headers=HEADERS, timeout=15)
        if res.status_code == 200:
            for item in res.json().get('message', {}).get('items', []):
                py = item.get('published', {}).get('date-parts', [[0]])[0][0]
                od = item.get('published-online', {}).get('date-parts') or item.get('created', {}).get('date-parts')
                papers.append({
                    'Date Available Online': standardize_date(od),
                    'LCDS Author': name,
                    'Paper Title': item.get('title', [''])[0],
                    'Journal Name': item.get('container-title', [''])[0] or "Preprint/Other",
                    'Publication Type': "Preprint" if item.get('type') == 'posted-content' else "Journal Article",
                    'Citation Count': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{item['DOI']}" if 'DOI' in item else None,
                    'Year': py if py != 0 else "Preprint"
                })
    except: pass
    return papers

if __name__ == "__main__":
    staff = get_staff_list()
    all_results = []
    with ThreadPoolExecutor(max_workers=8) as exc:
        futures = {exc.submit(fetch_papers, n): n for n in staff}
        for f in as_completed(futures): all_results.extend(f.result())
    
    if all_results:
        df = pd.DataFrame(all_results)
        df = df.drop_duplicates(subset=['DOI']).sort_values('Date Available Online', ascending=False)
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/lcds_publications.csv", index=False)
