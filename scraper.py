import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime

# --- CONFIGURATION ---
HEADERS = {'User-Agent': 'LCDS-Tracker/Stable-v1'}
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

        # 2. Sidebars
        for h3 in soup.select("h3.paragraph-side-title"):
            names.add(h3.get_text(strip=True))

        # 3. Clean
        clean_names = []
        for raw in names:
            n = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            if len(n) > 3 and "View profile" not in n:
                clean_names.append(n)

        # 4. Force Inclusions (The "Must Have" List)
        leads = ["Melinda Mills", "Jennifer Dowd", "Thomas Rawson", "Per Block", "Andrew Stephen", "Ridhu Kashyap", "Wen Su"]
        for l in leads:
            if l not in clean_names: clean_names.append(l)
            
        return sorted(list(set(clean_names)))
    except Exception as e:
        print(f"❌ Scrape Error: {e}")
        return ["Melinda Mills", "Jennifer Dowd", "Andrew Stephen"]

# --- 2. ORCID IDENTIFICATION (With Identity Traps) ---
def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for person in results:
                affils = " ".join([a.get('institution', {}).get('display_name', '').lower() for a in person.get('affiliations', [])])
                affils += " " + person.get('last_known_institution', {}).get('display_name', '').lower()
                
                # --- TRAP: ANDREW STEPHEN ---
                if "andrew stephen" in name.lower():
                    # Reject Oncologist/Geneticist
                    if any(x in affils for x in ["oncology", "genetics", "surgery", "medicine"]): continue 
                    # Accept Business/Marketing
                    if any(x in affils for x in ["marketing", "business", "saïd", "management", "retail"]):
                        return person['orcid'].split('/')[-1]
                    continue

                # --- STANDARD CHECKS ---
                if "oxford" not in affils: continue
                
                # Wen Su Override
                if "wen su" in name.lower(): return person['orcid'].split('/')[-1]

                # General Topics
                valid = ["demographic", "sociology", "nuffield", "leverhulme", "zoology", "economics", "epidemiology", "public health", "statistics"]
                if any(v in affils for v in valid):
                    return person['orcid'].split('/')[-1]
                    
    except: pass
    return None

# --- 3. FETCH WORKS ---
def fetch_works(name, orcid):
    works = []
    try:
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-09-01&sort=created&order=desc&rows=60"
        r = requests.get(url, headers=HEADERS, timeout=10)
        
        if r.status_code == 200:
            for item in r.json().get('message', {}).get('items', []):
                # Date
                d = item.get('created', {}).get('date-parts', [[2020,1,1]])[0]
                date_str = f"{d[0]}-{d[1]:02d}-01" if len(d)>=2 else f"{d[0]}-01-01"
                
                # Country Enrichment (Quick)
                countries = ""
                try:
                    if 'DOI' in item:
                        oa_url = f"https://api.openalex.org/works/doi:https://doi.org/{item['DOI']}?select=authorships"
                        oa_r = requests.get(oa_url, headers=HEADERS, timeout=2)
                        if oa_r.status_code == 200:
                            cs = set()
                            for a in oa_r.json().get('authorships', []):
                                for i in a.get('institutions', []):
                                    if i.get('country_code'): cs.add(i['country_code'])
                            countries = ",".join(cs)
                except: pass

                works.append({
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
    return works

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Collecting data for {len(staff)} researchers...")
    print("    (This handles data in memory to prevent file corruption)")
    
    # COLLECT ALL DATA IN MEMORY FIRST
    all_data = []
    for person in staff:
        print(f"    Processing {person}...", end=" ", flush=True)
        orcid = get_orcid(person)
        if orcid:
            new_works = fetch_works(person, orcid)
            all_data.extend(new_works)
            print(f"Found {len(new_works)} works.")
        else:
            print("No ORCID match.")

    # SAVE ONCE AT THE END
    if all_data:
        df = pd.DataFrame(all_data)
        # Deduplicate strictly by DOI
        df = df.drop_duplicates(subset=['DOI'])
        df.to_csv(CSV_FILE, index=False)
        print(f"\n✅ SUCCESS: Database updated with {len(df)} unique publications.")
    else:
        print("\n⚠️ No data found.")
