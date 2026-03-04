import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime

# --- CONFIGURATION ---
HEADERS = {'User-Agent': 'LCDS-Tracker/Production-v2'}
CSV_FILE = "data/lcds_publications.csv"

# --- 1. STAFF DISCOVERY ---
def get_staff_list():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. Main Grid
        for div in soup.select("div.views-field-title span.field-content"):
            names.add(div.get_text(strip=True))

        # 2. Sidebars (Leads)
        for h3 in soup.select("h3.paragraph-side-title"):
            names.add(h3.get_text(strip=True))

        # 3. Clean & Filter
        clean_names = []
        for raw in names:
            n = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            # Basic junk filter
            if len(n) > 3 and "View profile" not in n and "Read more" not in n:
                clean_names.append(n)

        # 4. HARDCODED INCLUSIONS (Ensure these key people are always checked)
        leads = ["Melinda Mills", "Jennifer Dowd", "Thomas Rawson", "Per Block", "Andrew Stephen", "Ridhu Kashyap", "Wen Su"]
        for l in leads:
            if l not in clean_names: clean_names.append(l)
            
        return sorted(list(set(clean_names)))
    except Exception as e:
        print(f"❌ Scrape Error: {e}")
        return ["Melinda Mills", "Andrew Stephen", "Wen Su"]

# --- 2. ORCID WITH "ANDREW STEPHEN" TRAP ---
def get_orcid(name):
    try:
        # Search OpenAlex
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for person in results:
                # Get all affiliation text
                affils = " ".join([a.get('institution', {}).get('display_name', '').lower() for a in person.get('affiliations', [])])
                affils += " " + person.get('last_known_institution', {}).get('display_name', '').lower()
                
                # --- TRAP: ANDREW STEPHEN ---
                if "andrew stephen" in name.lower():
                    # REJECT the Oncologist
                    if any(x in affils for x in ["oncology", "genetics", "surgery", "hospital", "medicine", "clinical"]):
                        continue 
                    # ACCEPT the Marketer
                    if any(x in affils for x in ["marketing", "business", "saïd", "management", "retail", "consumer"]):
                        return person['orcid'].split('/')[-1]
                    # If neither, skip to be safe
                    continue

                # --- STANDARD LOGIC FOR OTHERS ---
                # Must be Oxford
                if "oxford" not in affils: continue
                
                # Must be Relevant Field (Demography, Soc, Econ, etc.)
                valid_topics = ["demographic", "sociology", "nuffield", "leverhulme", "zoology", "economics", "epidemiology", "public health", "statistics", "social policy"]
                
                # Special Handler for Wen Su (Engineering allowed if Oxford)
                if "wen su" in name.lower() and "oxford" in affils:
                     return person['orcid'].split('/')[-1]

                # General Check
                if any(v in affils for v in valid_topics):
                    return person['orcid'].split('/')[-1]
                    
    except: pass
    return None

# --- 3. FETCH WORKS ---
def fetch_works(staff):
    all_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Processing {len(staff)} researchers...")
    
    for name in staff:
        print(f"   - {name}...", end=" ")
        orcid = get_orcid(name)
        
        if not orcid:
            print("No Match.")
            continue
            
        print(f"Found ({orcid})")
        
        try:
            # Fetch papers since 2019
            url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-09-01&sort=created&order=desc&rows=60"
            r = requests.get(url, headers=HEADERS, timeout=10)
            
            if r.status_code == 200:
                items = r.json().get('message', {}).get('items', [])
                for item in items:
                    # 1. Date
                    d = item.get('created', {}).get('date-parts', [[2020,1,1]])[0]
                    date_str = f"{d[0]}-{d[1]:02d}-01" if len(d)>=2 else f"{d[0]}-01-01"
                    
                    # 2. Country Enrichment (Lite)
                    countries = ""
                    try:
                        if 'DOI' in item:
                            oa_url = f"https://api.openalex.org/works/doi:https://doi.org/{item['DOI']}?select=authorships"
                            oa_r = requests.get(oa_url, headers=HEADERS, timeout=3)
                            if oa_r.status_code == 200:
                                cs = set()
                                for a in oa_r.json().get('authorships', []):
                                    for i in a.get('institutions', []):
                                        if i.get('country_code'): cs.add(i['country_code'])
                                countries = ",".join(cs)
                    except: pass

                    all_data.append({
                        'Date': date_str,
                        'Year': d[0],
                        'LCDS Author': name,
                        'Title': item.get('title', ['Untitled'])[0],
                        'Journal': item.get('container-title', [''])[0],
                        'Type': 'Preprint' if item.get('subtype')=='preprint' else 'Article',
                        'Citations': item.get('is-referenced-by-count', 0),
                        'DOI': item.get('DOI'),
                        'Countries': countries
                    })
        except: pass

    return all_data

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    
    # 1. Get List
    staff = get_staff_list()
    
    # 2. Fetch Data
    data = fetch_works(staff)
    
    # 3. Save (Single Write to prevent Corruption)
    if data:
        df = pd.DataFrame(data)
        # Deduplicate by DOI
        df = df.drop_duplicates(subset=['DOI'])
        df.to_csv(CSV_FILE, index=False)
        print(f"✅ Success! Saved {len(df)} publications to {CSV_FILE}")
    else:
        print("⚠️ No data found.")
