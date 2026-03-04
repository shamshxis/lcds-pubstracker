import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/6.0 (mailto:{mailto})'}

# --- 1. ROBUST STAFF DISCOVERY ---
def get_staff_list():
    """
    Scrapes LCDS website using a 'Density Check' to find names.
    This avoids relying on specific CSS tags that might change.
    """
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # STRATEGY: Grab every likely name container
        # We look for h3 tags (often used for names) and links inside content divs
        potential_names = []
        
        # 1. H3 Tags (Most common for profiles)
        for h3 in soup.find_all('h3'):
            potential_names.append(h3.get_text(strip=True))
            
        # 2. Links inside 'view-content' or 'grid' divs
        for div in soup.find_all('div', class_=lambda x: x and ('view' in x or 'grid' in x)):
            for a in div.find_all('a'):
                text = a.get_text(strip=True)
                if len(text) > 3: potential_names.append(text)

        # CLEANING & FILTERING
        clean_names = set()
        for raw in potential_names:
            # Remove Titles
            clean = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            
            # Junk Filter (Navigation terms)
            junk = ["View profile", "Read more", "Contact", "Email", "Research", "Team", "Profile", "News", "Events"]
            if any(x.lower() in clean.lower() for x in junk): continue
            
            # Validation: Must be 2+ words, no numbers, < 40 chars
            if len(clean.split()) >= 2 and len(clean) < 40 and not any(char.isdigit() for char in clean):
                clean_names.add(clean)

        # HARDCODED SAFETY NET (Ensure these key people are NEVER missed)
        clean_names.add("Melinda Mills")
        clean_names.add("Jennifer Dowd")
        clean_names.add("Thomas Rawson") # Zoology/Epi
        clean_names.add("Per Block")
        clean_names.add("Ridhu Kashyap")
        
        final_list = sorted(list(clean_names))
        print(f"✅ Found {len(final_list)} potential researchers.")
        return final_list

    except Exception as e:
        print(f"❌ Scrape error: {e}")
        # Fallback if site is down
        return ["Melinda Mills", "Jennifer Dowd", "Thomas Rawson"]

# --- 2. ORCID WITH "SMART AFFILIATION" ---
def get_orcid(name):
    """
    3-STEP VERIFICATION:
    1. OXFORD CHECK: Must have 'Oxford' in affiliation history.
    2. TOPIC CHECK: Must match Demography, Sociology, Zoology (for Rawson), etc.
    3. BAN CHECK: Kills Engineers (Wen Su) and Admins (Louise).
    """
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for person in results:
                # Get all affiliation info
                affils = [a.get('institution', {}).get('display_name', '').lower() for a in person.get('affiliations', [])]
                last_known = person.get('last_known_institution', {}).get('display_name', '').lower()
                affils.append(last_known)
                
                # Get Topics (Works count in specific fields)
                # (OpenAlex provides a 'x_concepts' or similar summary sometimes, but we stick to text for speed)
                full_text = " ".join(affils)
                
                # --- RULE 1: MUST BE OXFORD ---
                if "oxford" not in full_text: continue
                
                # --- RULE 2: RELEVANT FIELDS ---
                # Added 'zoology' specifically for Thomas Rawson
                valid_topics = [
                    "demographic", "sociology", "nuffield", "leverhulme", 
                    "population", "social policy", "zoology", "economics", 
                    "epidemiology", "public health", "statistics"
                ]
                if not any(t in full_text for t in valid_topics): continue
                
                # --- RULE 3: BAN LIST (Admins & Engineers) ---
                # "Wen Su" (Engineer) -> Banned
                # "Louise Allcock" (Admin) -> Banned
                ban_list = [
                    "civil engineering", "materials science", "structural", 
                    "administrator", "coordinator", "finance", "assistant", "manager"
                ]
                # Exception: If they explicitly say "Demography", ignore the ban (e.g. a Manager of Demography)
                if any(b in full_text for b in ban_list) and "demographic" not in full_text:
                    continue
                
                # If passed all checks
                return person['orcid'].replace('https://orcid.org/', '')
                
    except: pass
    print(f"   ❌ Skipping {name} (No valid Researcher ORCID found)")
    return None

# --- 3. FETCH WORKS (Your Proven Logic) ---
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
        # Crossref First + Created Date (Proven to catch recent papers)
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
                    'Field': 'Pending',
                    'Countries': ''
                })
    except: pass
    return works

# --- 4. ENRICH (Map Data) ---
def safe_enrich(df):
    if df.empty: return df
    print(f"[{datetime.now().time()}] 🧠 Enriching data for map...")
    try:
        dois = df['DOI'].str.replace('https://doi.org/', '').tolist()
        doi_map = {}
        
        def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
        
        for chunk in chunker(dois, 30):
            try:
                f = "|".join([f"doi:https://doi.org/{d}" for d in chunk])
                url = f"https://api.openalex.org/works?filter={f}&per-page=50&select=doi,primary_topic,authorships"
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code == 200:
                    for res in r.json().get('results', []):
                        d = res.get('doi', '').replace('https://doi.org/', '').lower()
                        
                        topic = "Multidisciplinary"
                        if res.get('primary_topic'): topic = res['primary_topic']['field']['display_name']
                        
                        cntry = set()
                        for a in res.get('authorships', []):
                            for i in a.get('institutions', []):
                                if i.get('country_code'): cntry.add(i['country_code'])
                        
                        doi_map[d] = {'Field': topic, 'Countries': ",".join(cntry)}
            except: pass
            
        for index, row in df.iterrows():
            d_key = row['DOI'].replace('https://doi.org/', '').lower()
            if d_key in doi_map:
                df.at[index, 'Field'] = doi_map[d_key]['Field']
                df.at[index, 'Countries'] = doi_map[d_key]['Countries']
    except: pass
    return df

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    all_data = []
    # 5 workers to be safe
    with ThreadPoolExecutor(max_workers=5) as exc:
        futures = {exc.submit(fetch_works, n, get_orcid(n)): n for n in staff}
        for f in as_completed(futures):
            res = f.result()
            if res: all_data.extend(res)
            
    if all_data:
        df = pd.DataFrame(all_data)
        df = df.sort_values('Date', ascending=False).drop_duplicates('DOI')
        df.to_csv("data/lcds_publications.csv", index=False)
        
        df = safe_enrich(df)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"✅ SUCCESS: Saved {len(df)} records.")
    else:
        pd.DataFrame(columns=['Date','Year','LCDS Author','Title','Journal','Type','Citations','DOI','Field','Countries']).to_csv("data/lcds_publications.csv", index=False)
