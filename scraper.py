import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/11.0 (mailto:{mailto})'}
CSV_FILE = "data/lcds_publications.csv"

# --- 1. STAFF DISCOVERY (Layout-Aware) ---
def get_staff_list():
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # SOURCE 1: Main Grid (Postdocs, Researchers)
        # In your HTML, these are inside div.views-field-title -> span.field-content
        for div in soup.select("div.views-field-title span.field-content"):
            text = div.get_text(strip=True)
            if len(text) > 3: names.add(text)

        # SOURCE 2: Sidebar/Leads (Melinda Mills, etc.)
        # In your HTML, these are h3.paragraph-side-title
        for h3 in soup.select("h3.paragraph-side-title"):
            text = h3.get_text(strip=True)
            if len(text) > 3: names.add(text)

        # CLEANING
        clean_names = set()
        for raw in names:
            clean = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            # Remove junk that looks like a name
            if any(x in clean for x in ["View profile", "Read more", "Contact", "Email"]): continue
            if len(clean.split()) >= 2 and len(clean) < 40 and not any(char.isdigit() for char in clean):
                clean_names.add(clean)

        # SAFETY NET (Hardcoded overrides for tricky profiles)
        leads = ["Melinda Mills", "Jennifer Dowd", "Thomas Rawson", "Per Block", "Andrew Stephen", "Ridhu Kashyap", "Wen Su"]
        for l in leads: clean_names.add(l)
        
        final_list = sorted(list(clean_names))
        print(f"✅ Found {len(final_list)} researchers.")
        return final_list

    except Exception as e:
        print(f"❌ Scrape error: {e}")
        return ["Melinda Mills", "Jennifer Dowd", "Andrew Stephen", "Wen Su"]

# --- 2. ORCID WITH SMART FILTERING ---
def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for person in results:
                # Compile all affiliation text
                affils = " ".join([a.get('institution', {}).get('display_name', '').lower() for a in person.get('affiliations', [])])
                affils += " " + person.get('last_known_institution', {}).get('display_name', '').lower()
                
                # RULE 1: MUST be Oxford
                if "oxford" not in affils: continue
                
                # RULE 2: Andrew Stephen Exception (Business vs Medicine)
                if "andrew stephen" in name.lower():
                    if any(x in affils for x in ["marketing", "business", "saïd", "management"]):
                        return person['orcid'].replace('https://orcid.org/', '')
                    else:
                        continue # Skip the oncologist
                
                # RULE 3: General Topic Match
                # We removed "Engineering" ban for Wen Su, but require Demography connection
                valid = ["demographic", "sociology", "nuffield", "leverhulme", "zoology", "economics", "epidemiology", "public health", "statistics", "social policy"]
                
                if any(v in affils for v in valid):
                    return person['orcid'].replace('https://orcid.org/', '')
                
                # Fallback: If they are at Oxford and have "Population" or "Health" in affiliation
                if "population" in affils or "global health" in affils:
                    return person['orcid'].replace('https://orcid.org/', '')

    except: pass
    return None

# --- 3. FETCH WORKS (Instant Enrichment) ---
def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        # Crossref First (Proven Logic)
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-09-01&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                # Date Parsing
                d = item.get('published-online') or item.get('created') or item.get('published-print')
                date_str = datetime.now().strftime('%Y-%m-%d')
                if d and 'date-parts' in d:
                    p = d['date-parts'][0]
                    date_str = f"{p[0]:04d}-{p[1]:02d}-{p[2]:02d}" if len(p)==3 else f"{p[0]:04d}-{p[1]:02d}-01"

                # Country Enrichment (Row-by-Row to prevent data loss)
                countries = ""
                try:
                    if 'DOI' in item:
                        doi_url = f"https://api.openalex.org/works/doi:https://doi.org/{item['DOI']}?select=authorships"
                        oa_r = requests.get(doi_url, headers=HEADERS, timeout=5)
                        if oa_r.status_code == 200:
                            c_set = set()
                            for a in oa_r.json().get('authorships', []):
                                for i in a.get('institutions', []):
                                    if i.get('country_code'): c_set.add(i['country_code'])
                            countries = ",".join(c_set)
                except: pass

                works.append({
                    'Date': date_str,
                    'Year': date_str.split('-')[0],
                    'LCDS Author': name,
                    'Title': item.get('title', ['Untitled'])[0],
                    'Journal': item.get('container-title', [''])[0] if item.get('container-title') else "Preprint",
                    'Type': "Preprint" if item.get('subtype')=='preprint' else "Article",
                    'Citations': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{item.get('DOI')}",
                    'Countries': countries
                })
    except: pass
    return works

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # Initialize CSV
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=['Date','Year','LCDS Author','Title','Journal','Type','Citations','DOI','Countries']).to_csv(CSV_FILE, index=False)

    staff = get_staff_list()
    print(f"[{datetime.now().time()}] 🚀 Starting fetch for {len(staff)} researchers...")
    
    # Process Row-by-Row (Fail-Safe)
    for person in staff:
        print(f"   Processing {person}...")
        orcid = get_orcid(person)
        if orcid:
            data = fetch_works(person, orcid)
            if data:
                df_new = pd.DataFrame(data)
                df_new.to_csv(CSV_FILE, mode='a', header=False, index=False)
    
    # Final Deduplication
    try:
        df = pd.read_csv(CSV_FILE)
        df = df.drop_duplicates(subset=['DOI'])
        df.to_csv(CSV_FILE, index=False)
        print("✅ Done.")
    except: pass
