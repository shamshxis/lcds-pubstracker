import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime
import re

# --- CONFIGURATION ---
mailto = os.environ.get('USER_EMAIL', 'research_tracker@ox.ac.uk')
HEADERS = {'User-Agent': f'LCDS-Tracker/12.0 (mailto:{mailto})'}
CSV_FILE = "data/lcds_publications.csv"
START_DATE = "2019-09-01"

# --- 1. STAFF DISCOVERY & ADMIN FILTERING ---
def get_staff_list():
    print(f"[{datetime.now().time()}] 🔍 Scanning LCDS website.")
    url = "https://www.demography.ox.ac.uk/people"
    names = set()

    # Explicit exclusions (Admin / Non-research)
    blocklist = ["hamza shams", "louise allcock", "admin", "administrator"]

    # Core researchers to guarantee inclusion
    leads = ["Melinda Mills", "Jennifer Dowd", "Thomas Rawson", "Per Block", "Andrew Stephen", "Ridhu Kashyap", "Charles Rahal"]
    for l in leads:
        names.add(l)

    admin_keywords = [
        "admin", "administrator", "manager", "coordinator", "officer", "assistant",
        "communications", "support", "hr", "finance", "alumni"
    ]

    def _is_current_member(position_text: str) -> bool:
        if not position_text:
            return True
        t = position_text.strip().lower()

        # Exclude obvious former-member patterns visible on the People page
        if "previously" in t:
            return False
        if re.search(r"\b(19|20)\d{2}\s*[-–]\s*(19|20)\d{2}\b", t):
            return False
        if "lcds postdoc" in t or "lcds dphil" in t:
            # Many former members are listed with a current external role plus prior LCDS role
            if "previously" in t or "(" in t:
                return False

        return True

    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        for card in soup.select(".views-row"):
            card_text = card.get_text(separator=" ", strip=True).lower()

            # Skip admin/support cards
            if any(k in card_text for k in admin_keywords):
                continue

            # Name selector based on the current card markup in the People page HTML
            name_el = card.select_one("h3.paragraph-side-title")
            if not name_el:
                # Fallback to older selector if Drupal theme changes again
                name_el = card.select_one("div.views-field-title span.field-content")
            if not name_el:
                continue

            raw_name = name_el.get_text(strip=True)
            clean = raw_name.replace("Dr ", "").replace("Prof ", "").replace("Professor ", "").strip()
            clean_lower = clean.lower()

            if any(b in clean_lower for b in blocklist):
                continue
            if len(clean.split()) < 2 or len(clean) > 40:
                continue

            # Pull position text to drop former members reliably
            pos_el = card.select_one(".field--name-field-position")
            position_text = pos_el.get_text(" ", strip=True) if pos_el else ""
            if not _is_current_member(position_text):
                continue

            names.add(clean)

        final_list = sorted(list(names))
        print(f"✅ Found {len(final_list)} current people (Admin/Support staff excluded).")
        return final_list

    except Exception as e:
        print(f"❌ Scrape error: {e}")
        return leads

# --- 2. STRICT ORCID FILTER ---
def get_orcid(name):
    """Find best-matching ORCID for a person name.

    Priority:
      1) Crossref works search (extract ORCID from author blocks)
      2) OpenAlex author search as a fallback

    OpenAlex is used only to validate Oxford/LCDS affiliation and to fill gaps.
    """
    def _split_name(full_name: str):
        parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
        if len(parts) < 2:
            return ("", "")
        family = parts[-1]
        given = " ".join(parts[:-1])
        return (given, family)

    def _author_name_matches(author_obj: dict, target_name: str) -> bool:
        given_t, family_t = _split_name(target_name)
        given_a = (author_obj.get("given") or "").strip()
        family_a = (author_obj.get("family") or "").strip()
        if not family_a or not family_t:
            return False

        # Family name: allow multi-word family names in Crossref (match end token)
        if family_t.lower() != family_a.split()[-1].lower():
            return False

        # Given name: at least initial should match when present
        if given_t and given_a:
            if given_t[0].lower() != given_a[0].lower():
                return False

        return True

    def _validate_orcid_via_openalex(orcid: str):
        """Return (score, oxford_flag, lcds_flag). Higher score is better."""
        try:
            url = f"https://api.openalex.org/authors/orcid:{orcid}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                return (0, False, False)

            j = r.json()
            inst_names = []
            for a in (j.get("affiliations") or []):
                dname = ((a.get("institution") or {}).get("display_name") or "").lower()
                if dname:
                    inst_names.append(dname)

            lki = ((j.get("last_known_institution") or {}).get("display_name") or "").lower()
            if lki:
                inst_names.append(lki)

            affils = " ".join(inst_names)
            oxford = "oxford" in affils
            lcds = ("leverhulme" in affils) or ("demographic science" in affils) or ("lcds" in affils)

            # Soft support for broader Oxford demography ecosystem
            demo_related = any(k in affils for k in ["demograph", "population", "nuffield", "public health", "sociolog", "health", "fertilit", "comput", "data science"])

            score = 0
            if oxford:
                score += 2
            if lcds:
                score += 3
            if demo_related:
                score += 1

            return (score, oxford, lcds)
        except Exception:
            return (0, False, False)

    # Phase 1: Crossref-first extraction of ORCIDs from works metadata
    try:
        params = {
            "query.author": name,
            "rows": 100,
            "sort": "relevance",
            "order": "desc",
            "select": "DOI,title,author,created"
        }
        cr_r = requests.get("https://api.crossref.org/works", params=params, headers=HEADERS, timeout=30)
        if cr_r.status_code == 200:
            candidates = []
            items = (cr_r.json().get("message") or {}).get("items") or []
            for item in items:
                for a in (item.get("author") or []):
                    orcid_url = a.get("ORCID")
                    if not orcid_url:
                        continue
                    if not _author_name_matches(a, name):
                        continue
                    orcid = str(orcid_url).replace("https://orcid.org/", "").replace("http://orcid.org/", "").strip()
                    if not orcid:
                        continue

                    score, oxford, lcds = _validate_orcid_via_openalex(orcid)
                    # Require at least Oxford or LCDS signal to avoid homonyms
                    if score >= 2:
                        candidates.append((score, orcid))

            if candidates:
                candidates.sort(reverse=True)
                return candidates[0][1]
    except Exception as e:
        print(f"      [!] Crossref ORCID discovery failed for {name}: {e}")

    # Phase 2: OpenAlex fallback search for ORCID (gap filler)
    try:
        r = requests.get("https://api.openalex.org/authors", params={"search": name, "per-page": 25}, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None

        best = (0, None)
        for person in r.json().get("results", []):
            orcid_val = person.get("orcid")
            if not orcid_val:
                continue
            orcid = str(orcid_val).replace("https://orcid.org/", "").strip()
            if not orcid:
                continue

            score, _, _ = _validate_orcid_via_openalex(orcid)
            if score > best[0]:
                best = (score, orcid)

        return best[1]
    except Exception as e:
        print(f"      [!] OpenAlex ORCID fallback error for {name}: {e}")

    return None
            
        results = r.json().get('results',[])
        for person in results:
            affil_names =[]
            
            # Extract all known affiliations
            for a in (person.get('affiliations') or[]):
                dname = (a.get('institution') or {}).get('display_name') or ""
                affil_names.append(str(dname).lower())
                
            lki_name = (person.get('last_known_institution') or {}).get('display_name') or ""
            affil_names.append(str(lki_name).lower())
            
            affils = " ".join(affil_names)
            
            # 1. MUST be affiliated with Oxford or LCDS
            if not any(req in affils for req in["oxford", "leverhulme", "lcds", "nuffield"]):
                continue
            
            # 2. MUST match relevant topics
            valid_topics =[
                "demograph", "sociology", "social", "health", "economic", 
                "pandemic", "epidemiology", "nuffield", "leverhulme", "lcds",
                "policy", "zoology", "marketing", "business", "saïd"
            ]
            if not any(k in affils for k in valid_topics):
                continue
            
            # 3. MUST NOT be purely medical/engineering with the same name
            banned_topics =["surgery", "oncology", "cancer", "civil engineering", "materials", "physics", "clinical"]
            if any(b in affils for b in banned_topics) and not any(v in affils for v in ["demograph", "sociology", "social", "pandemic"]):
                continue
            
            orcid_val = person.get('orcid')
            if orcid_val:
                return str(orcid_val).replace('https://orcid.org/', '')
                
    except Exception as e:
        print(f"      [!] ORCID Error for {name}: {e}")
        
    return None

def normalize_doi(doi_str):
    if not doi_str: return ""
    return doi_str.lower().replace('https://doi.org/', '').replace('http://doi.org/', '').strip()

# --- 3. FETCH PUBLICATIONS (CROSSREF + OPENALEX GAP FILL) ---
def fetch_works(name, orcid):
    works_dict = {}
    if not orcid: return[]
    
    # -- PHASE 1: CROSSREF --
    try:
        cr_url = f"https://api.crossref.org/works?filter=orcid:{orcid},from-pub-date:{START_DATE}&sort=created&order=desc&rows=100"
        cr_r = requests.get(cr_url, headers=HEADERS, timeout=30)
        
        if cr_r.status_code == 200:
            for item in cr_r.json().get('message', {}).get('items',[]):
                # Safe Date Parsing
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
                journals = item.get('container-title') or []
                journal_str = str(journals[0]) if journals else "Preprint"
                
                doi_val = normalize_doi(item.get('DOI'))
                subtype = item.get('subtype')
                is_preprint = subtype == 'preprint' or journal_str.lower() in['preprint', 'medrxiv', 'biorxiv', 'socarxiv', 'ssrn', 'osf']

                # Country Enrichment
                countries = ""
                if doi_val:
                    try:
                        time.sleep(0.05)
                        oa_r = requests.get(f"https://api.openalex.org/works/doi:https://doi.org/{doi_val}?select=authorships", headers=HEADERS, timeout=5)
                        if oa_r.status_code == 200:
                            c_set = {str(i.get('country_code')) for a in (oa_r.json().get('authorships') or []) for i in (a.get('institutions') or[]) if i.get('country_code')}
                            countries = ",".join(c_set)
                    except: pass

                work_obj = {
                    'Date': date_str, 'Year': date_str.split('-')[0], 'LCDS Author': name,
                    'Title': title_str, 'Journal': journal_str,
                    'Type': "Preprint" if is_preprint else "Article",
                    'Citations': item.get('is-referenced-by-count', 0),
                    'DOI': f"https://doi.org/{doi_val}" if doi_val else "", 'Countries': countries
                }
                
                dict_key = doi_val if doi_val else title_str.lower()
                works_dict[dict_key] = work_obj
    except Exception as e:
        print(f"[!] CrossRef failed for {name}: {e}")

    # -- PHASE 2: OPENALEX GAP FILLER --
    try:
        oa_url = f"https://api.openalex.org/works?filter=author.orcid:https://orcid.org/{orcid},from_publication_date:{START_DATE}&per-page=100"
        oa_r = requests.get(oa_url, headers=HEADERS, timeout=30)
        
        if oa_r.status_code == 200:
            for item in oa_r.json().get('results',[]):
                doi_val = normalize_doi(item.get('doi'))
                title_str = str(item.get('title') or "Untitled")
                title_key = title_str.lower()
                
                # Skip if already captured by CrossRef
                if (doi_val and doi_val in works_dict) or (title_key in works_dict):
                    continue
                
                date_str = item.get('publication_date') or f"{item.get('publication_year', 2020)}-01-01"
                journal_str = "Preprint"
                is_preprint = False
                
                loc = item.get('primary_location') or {}
                source = loc.get('source') or {}
                if source:
                    journal_str = source.get('display_name') or "Preprint"
                    if source.get('type') == 'repository': is_preprint = True
                
                c_set = {str(i.get('country_code')) for a in (item.get('authorships') or[]) for i in (a.get('institutions') or[]) if i.get('country_code')}
                
                work_obj = {
                    'Date': date_str, 'Year': date_str.split('-')[0], 'LCDS Author': name,
                    'Title': title_str, 'Journal': journal_str,
                    'Type': "Preprint" if is_preprint else "Article",
                    'Citations': item.get('cited_by_count', 0),
                    'DOI': f"https://doi.org/{doi_val}" if doi_val else "", 'Countries': ",".join(c_set)
                }
                dict_key = doi_val if doi_val else title_key
                works_dict[dict_key] = work_obj
    except Exception as e:
        print(f"      [!] OpenAlex gap-fill failed for {name}: {e}")

    return list(works_dict.values())

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    staff = get_staff_list()
    
    if not os.path.exists(CSV_FILE):
        pd.DataFrame(columns=['Date','Year','LCDS Author','Title','Journal','Type','Citations','DOI','Countries']).to_csv(CSV_FILE, index=False, encoding='utf-8')

    print(f"[{datetime.now().time()}] 🚀 Starting fetch for {len(staff)} researchers...")
    
    for person in staff:
        print(f"   Processing {person}...")
        time.sleep(0.5) # Polite API delay
        
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
    
    # --- FINAL DEDUPLICATION ---
    try:
        print("\n🧹 Cleaning up and removing cross-author duplicates...")
        df = pd.read_csv(CSV_FILE, encoding='utf-8')
        
        has_doi = df['DOI'].notna() & (df['DOI'] != "")
        
        # Merge co-authored papers (combines LCDS Authors gracefully)
        df_dois = df[has_doi].groupby('DOI', as_index=False).agg({
            'Date': 'first', 'Year': 'first', 
            'LCDS Author': lambda x: ', '.join(sorted(set(x))), 
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
        print("✅ Done! Data is strictly filtered, gap-filled, deduplicated, and ready for Streamlit.")
    except Exception as e:
        print(f"❌ Clean-up error: {e}")
