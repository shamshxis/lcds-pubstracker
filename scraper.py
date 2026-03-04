import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
import traceback
import re
from datetime import datetime

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_tracker@ox.ac.uk')
HEADERS = {'User-Agent': f'LCDS-Tracker/11.0 (mailto:{mailto})'}
CSV_FILE = "data/lcds_publications.csv"
START_DATE = "2019-09-01"

# --- 1. STAFF DISCOVERY & ADMIN FILTERING ---
def get_staff_list():
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website...")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # PRIMARY: The Grid View
        for span in soup.select('div.views-field-title span.field-content'):
            names.add(span.get_text(strip=True))
            
        # SECONDARY: Side Titles
        for h3 in soup.select('h3.paragraph-side-title'):
            names.add(h3.get_text(strip=True))

        # CLEANING & CATEGORICAL ADMIN REMOVAL
        clean_names = set()
        admin_keywords =["admin", "administrator", "manager", "coordinator", "officer", "assistant", "director of", "communications", "support", "alumni", "hr ", "finance"]
        
        for raw in names:
            clean = raw.replace('Dr ', '').replace('Prof ', '').replace('Professor ', '').strip()
            clean_lower = clean.lower()
            
            # Reject if it contains an admin keyword
            if any(keyword in clean_lower for keyword in admin_keywords):
                continue
                
            if len(clean.split()) >= 2 and len(clean) < 40 and "view profile" not in clean_lower:
                clean_names.add(clean)

        # SAFETY NET (Hardcoded overrides for core researchers)
        leads =["Melinda Mills", "Jennifer Dowd", "Thomas Rawson", "Per Block", "Andrew Stephen", "Ridhu Kashyap", "Charles Rahal"]
        for l in leads: clean_names.add(l)
        
        final_list = sorted(list(clean_names))
        print(f"✅ Found {len(final_list)} researchers (Admin staff excluded).")
        return final_list

    except Exception as e:
        print(f"❌ Scrape error: {e}")
        return["Melinda Mills", "Jennifer Dowd", "Thomas Rawson"]

# --- 2. ORCID FILTER ---
def get_orcid(name):
    try:
        r = requests.get("https://api.openalex.org/authors", params={'search': name}, headers=HEADERS, timeout=10)
        
        if r.status_code != 200: return None
            
        results = r.json().get('results', [])
        for person in results:
            affil_names =[]
            # Extract current and last known affiliations
            for a in (person.get('affiliations') or[]):
                dname = (a.get('institution') or {}).get('display_name') or ""
                affil_names.append(str(dname).lower())
                
            lki_name = (person.get('last_known_institution') or {}).get('display_name') or ""
            affil_names.append(str(lki_name).lower())
            
            affils = " ".join(affil_names)
            
            # 1. MUST be Oxford affiliated
            if "oxford" not in affils: continue
            
            # 2. MUST match relevant topic/department
            valid =["demographic", "sociology", "nuffield", "leverhulme", "zoology", "economics", "epidemiology", "marketing", "business", "saïd", "social policy"]
            if not any(k in affils for k in valid): continue
            
            # 3. MUST NOT be an admin/wrong department match (e.g. Medics with same name)
            ban =["civil engineering", "materials science", "oncology", "surgery", "cancer", "administrator", "manager", "support", "clinical"]
            if any(b in affils for b in ban) and not any(x in affils for x in["demographic", "sociology", "leverhulme"]): continue
            
            orcid_val = person.get('orcid')
            if orcid_val:
                return str(orcid_val).replace('https://orcid.org/', '')
                
    except Exception as e:
        print(f"      [!] ORCID Error for {name}: {e}")
        
    return None

def normalize_doi(doi_str):
    if not doi_str: return ""
    return doi_str.lower().replace('https://doi.org/', '').replace('http://doi.org/', '').strip()

# --- 3. CROSSREF (PRIMARY) + OPENALEX (GAP FILLER) ---
def fetch_works(name, orcid):
    works_dict = {} # Keyed by DOI or Title to prevent duplicates
    if not orcid: return[]
    
    # ---------------------------------------------------------
    # PHASE 1: SCAN CROSSREF FIRST
    # ---------------------------------------------------------
    try:
        cr_url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{START_DATE}&sort=created&order=desc&rows=100"
        cr_r = requests.get(cr_url, headers=HEADERS, timeout=30)
        
        if cr_r.status_code == 200:
            for item in cr_r.json().get('message', {}).get('items',[]):
                # Safe Date
                d = item.get('published-online') or item.get('created') or item.get('published-print') or {}
                date_parts = d.get('date-parts') or[]
                date_str = datetime.now().strftime('%Y-%m-%d')
                if len(date_parts) > 0 and len(date_parts[0]) > 0:
                    p = date_parts[0]
                    if len(p) >= 3: date_str = f"{p[0]:04d}-{p[1]:02d}-{p[2]:02d}"
                    elif len(p) == 2: date_str = f"{p[0]:04d}-{p[1]:02d}-01"
                    elif len(p) == 1: date_str = f"{p[0]:04d}-01-01"

                titles = item.get('title') or[]
                title_str = str(titles[0]) if titles else "Untitled"
                journals = item.get('container-title') or[]
                journal_str = str(journals[0]) if journals else "Preprint"
                
                doi_val = normalize_doi(item.get('DOI'))
                subtype = item.get('subtype')
                is_preprint = subtype == 'preprint' or journal_str.lower() in['preprint', 'medrxiv', 'biorxiv', 'socarxiv', 'ssrn']

                # Fetch Country Enrichment via OpenAlex DOI lookup
                countries = ""
                if doi_val:
                    try:
                        time.sleep(0.05) # Polite delay
                        oa_r = requests.get(f"https://api.openalex.org/works/doi:https://doi.org/{doi_val}?select=authorships", headers=HEADERS, timeout=5)
                        if oa_r.status_code == 200:
                            c_set = {str(i.get('country_code')) for a in (oa_r.json().get('authorships') or []) for i in (a.get('institutions') or[]) if i.get('country_code')}
                            countries = ",".join(c_set)
                    except: pass

                work_obj = {
                    'Date': date_str,
                    'Year': date_str.split('-')[0],
                    'LCDS Author': name,
                    'Title': title_str,
                    'Journal': journal_str,
                    'Type': "Preprint" if is_preprint else "Article",
                    'Citations': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{doi_val}" if doi_val else "",
                    'Countries': countries
                }
                
                # Store by DOI if exists, else by Title
                dict_key = doi_val if doi_val else title_str.lower()
                works_dict[dict_key] = work_obj
    except Exception as e:
        print(f"      [!] CrossRef failed for {name}: {e}")

    # ---------------------------------------------------------
    # PHASE 2: OPENALEX (FILL MISSING PREPRINTS / GAPS)
    # ---------------------------------------------------------
    try:
        oa_url = f"https://api.openalex.org/works?filter=author.orcid:https://orcid.org/{orcid},from_publication_date:{START_DATE}&per-page=100"
        oa_r = requests.get(oa_url, headers=HEADERS, timeout=30)
        
        if oa_r.status_code == 200:
            for item in oa_r.json().get('results',[]):
                doi_val = normalize_doi(item.get('doi'))
                title_str = str(item.get('title') or "Untitled")
                title_key = title_str.lower()
                
                # --- GAP CHECK: If we already have this via CrossRef, SKIP IT ---
                if (doi_val and doi_val in works_dict) or (title_key in works_dict):
                    continue
                
                # Otherwise, it's a gap! Add it.
                date_str = item.get('publication_date') or f"{item.get('publication_year', 2020)}-01-01"
                
                journal_str = "Preprint"
                is_preprint = False
                loc = item.get('primary_location') or {}
                source = loc.get('source') or {}
                if source:
                    journal_str = source.get('display_name') or "Preprint"
                    type_str = source.get('type')
                    if type_str == 'repository': is_preprint = True
                
                # Instant Country Enrichment from OpenAlex response
                c_set = {str(i.get('country_code')) for a in (item.get('authorships') or []) for i in (a.get('institutions') or[]) if i.get('country_code')}
                
                work_obj = {
                    'Date': date_str,
                    'Year': date_str.split('-')[0],
                    'LCDS Author': name,
                    'Title': title_str,
                    'Journal': journal_str,
                    'Type': "Preprint" if is_preprint else "Article",
                    'Citations': item.get('cited_by_count', 0),
                    'DOI': f"https://doi.org/{doi_val}" if doi_val else "",
                    'Countries': ",".join(c_set)
                }
                
                dict_key = doi_val if doi_val else title_key
                works_dict[dict_key] = work_obj
    except Exception as e:
        print(f"      [!] OpenAlex gap-fill failed for {name}: {e}")

    return list(works_dict.values())

# --- MAIN ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=['Date','Year','LCDS Author','Title','Journal','Type','Citations','DOI','Countries']).to_csv(CSV_FILE, index=False, encoding='utf-8')

    print(f"[{datetime.now().time()}] 🚀 Starting fetch for {len(staff)} researchers...")
    
    for person in staff:
        print(f"   Processing {person}...")
        time.sleep(0.5) # Polite delay
        
        orcid = get_orcid(person)
        if orcid:
            data = fetch_works(person, orcid)
            if data:
                df_new = pd.DataFrame(data)
                try:
                    df_new.to_csv(CSV_FILE, mode='a', header=False, index=False, encoding='utf-8')
                    print(f"      ✅ Added {len(data)} works (CrossRef + Gaps)")
                except PermissionError:
                    print("      ❌ FATAL ERROR: CSV is open in Excel! Please close it and restart.")
                    break
            else:
                print("      ⚠️ No works found since 2019-09-01.")
        else:
            print("      ❌ No valid ORCID found.")
    
    # Final Deduplication & Cleanup
    try:
        print("\n🧹 Cleaning up and removing cross-author duplicates...")
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        
        # We need to deduplicate globally in case multiple LCDS authors collaborated on the same paper
        has_doi = df['DOI'].notna() & (df['DOI'] != "")
        
        # Combine LCDS Authors if there's a duplicate
        df_dois = df[has_doi].groupby('DOI', as_index=False).agg({
            'Date': 'first', 'Year': 'first', 
            'LCDS Author': lambda x: ', '.join(sorted(set(x))), # Merge multiple LCDS authors!
            'Title': 'first', 'Journal': 'first', 'Type': 'first', 
            'Citations': 'max', 'Countries': 'first'
        })
        
        df_no_dois = df[~has_doi].groupby('Title', as_index=False).agg({
            'Date': 'first', 'Year': 'first', 
            'LCDS Author': lambda x: ', '.join(sorted(set(x))), 
            'Journal': 'first', 'Type': 'first', 
            'Citations': 'max', 'DOI': 'first', 'Countries': 'first'
        })
        
        df_final = pd.concat([df_dois, df_no_dois])
        df_final = df_final.sort_values(by="Date", ascending=False)
        
        df_final.to_csv(CSV_FILE, index=False, encoding='utf-8')
        print("✅ Done! Data is strictly filtered, gap-filled, deduplicated, and ready.")
    except Exception as e:
        print(f"❌ Clean-up error: {e}")
