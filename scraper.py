import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Tracker/Final (mailto:{mailto})'}

# --- 1. STAFF DISCOVERY ---
def get_staff_list():
    """Scrapes LCDS website using your proven selectors + 'Kitchen Sink' backup."""
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Proven Selectors (from your Colab)
        selectors = [
            'h3.paragraph-side-title', 
            'div.person-name', 
            'span.field-content h3', 
            '.views-field-title a'
        ]
        
        for s in selectors:
            for el in soup.select(s):
                names.add(el.get_text(strip=True))

        # Backup: Find people hidden in links
        for a in soup.find_all('a', href=True):
            if '/people/' in a['href']:
                names.add(a.get_text(strip=True))

        # Cleaning
        clean_names = set()
        for raw in names:
            clean = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            junk = ["View profile", "Read more", "Contact", "Email", "Research", "Team", "Profile"]
            if any(x.lower() in clean.lower() for x in junk): continue
            
            # Must look like a name
            if len(clean.split()) >= 2 and len(clean) < 40 and not any(char.isdigit() for char in clean):
                clean_names.add(clean)

        # Hardcoded Leads (Ensure they are never missed)
        clean_names.add("Melinda Mills")
        clean_names.add("Jennifer Dowd")
        clean_names.add("Thomas Rawson") 
        
        final_list = sorted(list(clean_names))
        print(f"✅ Found {len(final_list)} potential staff on website.")
        return final_list

    except Exception as e:
        print(f"❌ Scrape error: {e}")
        return ["Melinda Mills", "Thomas Rawson"]

# --- 2. ORCID WITH "ADMIN FIREWALL" ---
def get_orcid(name):
    """
    STRICT FILTER:
    - Must be Oxford Affiliated.
    - Must match Research Keywords (Demography, Sociology, Zoology, etc).
    - Must NOT match Admin/Engineering keywords.
    """
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            results = r.json().get('results', [])
            
            for person in results:
                # Build full affiliation text (current + past + last known)
                affils = [a.get('institution', {}).get('display_name', '').lower() for a in person.get('affiliations', [])]
                last_known = person.get('last_known_institution', {}).get('display_name', '').lower()
                affils.append(last_known)
                full_text = " ".join(affils)
                
                # --- RULE 1: THE OXFORD CONNECTION ---
                if "oxford" not in full_text: 
                    continue # Skip if never been at Oxford
                
                # --- RULE 2: THE TOPIC WHITELIST ---
                # Added 'zoology' for Thomas Rawson, 'economics' for others
                valid_keywords = [
                    "demographic", "sociology", "nuffield", "leverhulme", 
                    "population", "social policy", "zoology", "economics", 
                    "public health", "epidemiology"
                ]
                if not any(k in full_text for k in valid_keywords):
                    continue # Skip if field is irrelevant
                
                # --- RULE 3: THE ADMIN/ENGINEER BANLIST ---
                # Filters out Louise Allcock (Admin) and Wen Su (Engineer)
                ban_keywords = [
                    "administrator", "coordinator", "manager", "finance", 
                    "civil engineering", "materials science", "structural engineering"
                ]
                if any(b in full_text for b in ban_keywords):
                    continue # Skip admins and engineers
                
                # If we pass all 3 rules, it's a match!
                return person['orcid'].replace('https://orcid.org/', '')
    except: pass
    
    print(f"   ❌ Skipping {name} (No valid Researcher ORCID found)")
    return None

# --- 3. FETCH WORKS (Unchanged) ---
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
    # CRITICAL: If get_orcid returned None, we STOP here.
    if not orcid: return [] 
    
    try:
        # Crossref First + Created Date Priority
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

# --- 4. ENRICH (Unchanged) ---
def safe_enrich(df):
    if df.empty: return df
    print(f"[{datetime.now().time()}] 🧠 Enriching data...")
    try:
        dois = df['DOI'].str.replace('https://doi.org/', '').tolist()
        doi_map = {}
        
        def chunker(seq, size): return (seq[pos:pos + size] for pos in range(0, len(seq), size))
        
        for chunk in chunker(dois, 40):
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
    # 5 workers is safe
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
