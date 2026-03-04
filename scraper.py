import requests
from bs4 import BeautifulSoup
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION (Loaded from Environment Variables for Security) ---
# Set these in your GitHub Repository Secrets
mailto = os.environ.get('USER_EMAIL', 'research_team@example.com')
HEADERS = {'User-Agent': f'LCDS-Pubs-Tracker/2.0 (mailto:{mailto})'}

# --- HELPER FUNCTIONS ---
def get_staff_list():
    """Scrapes the LCDS People page for current staff."""
    url = "https://www.demography.ox.ac.uk/people"
    print(f"[{datetime.now().time()}] Fetching staff list...")
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        # Updated selectors based on standard Oxford Drupal templates
        selectors = ['.person-name', 'h3.node__title', '.views-field-title a']
        names = set()
        for s in selectors:
            for el in soup.select(s):
                n = el.get_text(strip=True)
                if n and len(n.split()) > 1:
                    names.add(n)
        
        # Manual additions if needed
        names.add("Ursula Gazeley")
        return sorted(list(names))
    except Exception as e:
        print(f"Error fetching staff: {e}")
        return ["Melinda Mills"] # Fallback

def get_affiliation_status(work_affiliations):
    """Determines if the work is attributed to LCDS, Oxford, or External."""
    if not work_affiliations:
        return "Unknown"
    
    # Normalize text for checking
    aff_text = " ".join([str(a).lower() for a in work_affiliations])
    
    if "leverhulme" in aff_text or "demographic science" in aff_text:
        return "LCDS (Core)"
    elif "oxford" in aff_text or "nuffield" in aff_text:
        return "Oxford (Other)"
    else:
        return "External/Previous"

def fetch_openalex_data(name):
    """Fetches works from OpenAlex with rich metadata (Topics, Affiliations)."""
    works = []
    try:
        # 1. Resolve Author ID
        url_author = "https://api.openalex.org/authors"
        params = {'search': name}
        r = requests.get(url_author, params=params, headers=HEADERS)
        if r.status_code != 200: return []
        
        results = r.json().get('results', [])
        if not results: return []
        
        # Simple heuristic: pick the first result or filter by Oxford-related context
        author_id = results[0]['id'] # OpenAlex ID (e.g., A5003636662)

        # 2. Fetch Works (Last 6 Years + Preprints)
        url_works = "https://api.openalex.org/works"
        # Filter: Author ID + Published since 2019
        filter_str = f"author.id:{author_id},publication_year:>2018"
        params_works = {'filter': filter_str, 'per-page': 200}
        
        rw = requests.get(url_works, params=params_works, headers=HEADERS)
        if rw.status_code == 200:
            items = rw.json().get('results', [])
            for item in items:
                # Extract Primary Topic/Field
                topic = "Multidisciplinary"
                if item.get('primary_topic'):
                    topic = item['primary_topic'].get('field', {}).get('display_name', 'Other')
                
                # Check Affiliation specific to this work
                authorships = item.get('authorships', [])
                my_affiliations = []
                for auth in authorships:
                    if auth.get('author', {}).get('id') == author_id:
                        my_affiliations = [inst.get('display_name', '') for inst in auth.get('institutions', [])]
                
                aff_status = get_affiliation_status(my_affiliations)

                works.append({
                    'Author': name,
                    'Title': item.get('display_name'),
                    'Journal': item.get('primary_location', {}).get('source', {}).get('display_name') or "Preprint/Other",
                    'Date': item.get('publication_date'),
                    'Year': item.get('publication_year'),
                    'DOI': item.get('doi'),
                    'Type': item.get('type'),
                    'Field': topic,
                    'Affiliation_Scope': aff_status,
                    'Citation_Count': item.get('cited_by_count', 0),
                    'Source': 'OpenAlex'
                })
    except Exception as e:
        print(f"Error for {name}: {e}")
    return works

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("Starting extraction...")
    staff = get_staff_list()
    print(f"Found {len(staff)} staff members.")
    
    all_data = []
    
    # Run in parallel for speed
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {executor.submit(fetch_openalex_data, name): name for name in staff}
        for future in as_completed(future_to_name):
            data = future.result()
            if data:
                all_data.extend(data)
                
    if all_data:
        df = pd.DataFrame(all_data)
        # Deduplicate by DOI, keeping the most recent record
        df = df.drop_duplicates(subset=['DOI'], keep='first')
        
        # Save to CSV
        os.makedirs("data", exist_ok=True)
        df.to_csv("data/lcds_publications.csv", index=False)
        print(f"Successfully saved {len(df)} records to data/lcds_publications.csv")
    else:
        print("No records found.")
