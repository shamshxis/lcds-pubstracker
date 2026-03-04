import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/9.0 (mailto:{mailto})'}

# --- 1. STAFF DISCOVERY ---
def get_staff_list():
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Selectors matching your HTML structure
        for div in soup.find_all("div", class_="views-field-title"):
            text = div.get_text(strip=True)
            if text: names.add(text)

        for h3 in soup.select("h3.paragraph-side-title"):
            names.add(h3.get_text(strip=True))

        clean_names = set()
        for raw in names:
            clean = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            junk = ["View profile", "Read more", "Contact", "Email", "Research", "Team", "Profile"]
            if any(x.lower() in clean.lower() for x in junk): continue
            
            if len(clean.split()) >= 2 and len(clean) < 40 and not any(char.isdigit() for char in clean):
                clean_names.add(clean)

        # Safety Net
        leads = ["Melinda Mills", "Jennifer Dowd", "Thomas Rawson", "Per Block", "Andrew Stephen", "Ridhu Kashyap"]
        for l in leads: clean_names.add(l)
        
        final_list = sorted(list(clean_names))
        print(f"✅ Found {len(final_list)} researchers.")
        return final_list

    except Exception as e:
        print(f"❌ Scrape error: {e}")
        return ["Melinda Mills", "Jennifer Dowd", "Andrew Stephen"]

# --- 2. ORCID WITH FIREWALL ---
def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for person in results:
                affils = [a.get('institution', {}).get('display_name', '').lower() for a in person.get('affiliations', [])]
                last_known = person.get('last_known_institution', {}).get('display_name', '').lower()
                affils.append(last_known)
                full_text = " ".join(affils)
                
                # Rule 1: Oxford
                if "oxford" not in full_text: continue
                
                # Rule 2: Topics (Includes Marketing for Andrew Stephen)
                valid = ["demographic", "sociology", "nuffield", "leverhulme", "zoology", "economics", 
                         "epidemiology", "public health", "statistics", "marketing", "business", "saïd"]
                if not any(k in full_text for k in valid): continue
                
                # Rule 3: Ban List (Blocks wrong Andrew Stephen & Admins)
                ban = ["civil engineering", "materials science", "oncology", "surgery", "cancer", "administrator", "finance"]
                
                is_banned = any(b in full_text for b in ban)
                # Override ban if they have "demographic" or "marketing"
                has_override = any(x in full_text for x in ["demographic", "marketing", "saïd"])
                
                if is_banned and not has_override: continue 
                
                return person['orcid'].replace('https://orcid.org/', '')
    except: pass
    return None

# --- 3. FETCH WORKS ---
def standardize_date(date_parts):
    try:
        if not date_parts: return None
        p = date_parts[0]
        if len(p) == 3: return "{:04d}-{:02d}-{:02d}".format(*p)
        if len(p) == 2: return "{:04d}-{:02d}-01".format(*p)
        return "{:04d}-01-01".format(*p)
    except: return None

def fetch_works(name, orcid):
    works = []
    if not orcid: return []
    try:
        # Crossref First (Proven Recent Logic)
        url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:2019-09-01&sort=created&order=desc&rows=100"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            items = r.json().get('message', {}).get('items', [])
            for item in items:
                is_pp = item.get('subtype') == 'preprint' or item.get('type') == 'posted-content'
                
                d_obj = item.get('published-online') or item.get('created') or item.get('published-print')
                final_date = datetime.now().strftime('%Y-%m-%d')
                if d_obj and 'date-parts' in d_obj:
                    final_date = standardize_date(d_obj['date-parts'])
                elif d_obj and 'date-time' in d_obj:
                    final_date = str(d_obj['date-time']).split('T')[0]

                works.append({
                    'Date': final_date,
                    'Year': final_date.split('-')[0],
                    'LCDS Author': name,
                    'Title': item.get('title', ['Untitled'])[0],
                    'Journal': item.get('container-title', [''])[0] if item.get('container-title') else ("Preprint" if is_pp else "Unknown"),
                    'Type': "Preprint" if is_pp else "Journal Article",
                    'Citations': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{item.get('DOI')}",
                    'Countries': '' # Initialize empty
                })
    except: pass
    return works

# --- 4. ENRICH (Get Countries) ---
def safe_enrich(df):
    if df.empty: return df
    print(f"[{datetime.now().time()}] 🧠 Enriching country data...")
    try:
        dois = df['DOI'].str.replace('https://doi.org/', '').tolist()
        doi_map = {}
        
        def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
        
        for chunk in chunker(dois, 40):
            try:
                f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
                # Explicitly ask for 'authorships' which contains countries
                url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,authorships"
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    for res in r.json().get('results', []):
                        d = res.get('doi', '').replace('https://doi.org/', '').lower()
                        
                        cntry = set()
                        for a in res.get('authorships', []):
                            for i in a.get('institutions', []):
                                if i.get('country_code'): cntry.add(i['country_code'])
                        
                        doi_map[d] = ",".join(cntry)
            except: pass
            
        for index, row in df.iterrows():
            d_key = row['DOI'].replace('https://doi.org/', '').lower()
            if d_key in doi_map:
                df.at[index, 'Countries'] = doi_map[d_key]
    except Exception as e: 
        print(f"Enrichment error: {e}")
    return df

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_data = []
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(fetch_works, n, get_orcid(n)): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.sort_values('Date', ascending=False).drop_duplicates('DOI')
        
        # 1. Save Basic Data (Safety)
        df.to_csv("data/lcds_publications.csv", index=False)
        
        # 2. Enrich with Countries & Save Again
        df = safe_enrich(df)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"✅ SUCCESS: Saved {len(df)} records.")
    else:
        # Save Empty Structure
        pd.DataFrame(columns=['Date','Year','LCDS Author','Title','Journal','Type','Citations','DOI','Countries']).to_csv("data/lcds_publications.csv", index=False)
