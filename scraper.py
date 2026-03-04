import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
mailto = os.environ.get("USER_EMAIL", "research_tracker@ox.ac.uk")
HEADERS = {"User-Agent": f"LCDS-Tracker/12.1 (mailto:{mailto})"}

PEOPLE_URL = os.environ.get(
    "PEOPLE_URL",
    "https://www.demography.ox.ac.uk/people",
)

CSV_FILE = "data/lcds_publications.csv"
START_DATE = os.environ.get("START_DATE", "2019-09-01")

# When names are ambiguous, do not guess an ORCID unless Oxford + LCDS evidence is strong.
STRICT_DISAMBIGUATION = os.environ.get("STRICT_DISAMBIGUATION", "1") != "0"

# --- KEYWORDS ---
ADMIN_KEYWORDS = {
    "administrator", "administration", "admin", "finance", "hr", "operations",
    "events", "communications", "comms", "outreach", "assistant", "pa",
    "personal assistant", "coordinator", "manager", "executive", "support",
    "web", "it", "systems", "data manager", "project manager"
}

FORMER_KEYWORDS = {
    "previously", "former", "past", "alumni", "ex-", "was", "until"
}

# Affiliation vocabulary for scoring and validation
OXFORD_TERMS = {
    "university of oxford", "oxford", "ox.ac.uk", "oxford population health",
    "nuffield department of population health", "ndph", "demographic science unit",
    "dunn school", "department of sociology", "oxford martin"
}
LCDS_TERMS = {
    "leverhulme centre for demographic science", "lcds", "leverhulme centre for demography",
    "leverhulme centre for demographic", "leverhulme centre", "demography.ox.ac.uk"
}

DOMAIN_TERMS = {
    "demograph", "population", "fertil", "mortali", "migration", "family",
    "epidemiolog", "public health", "health", "ageing", "aging",
    "inequal", "computational", "statistic", "social", "sociolog",
    "econom", "policy", "survey"
}


# --- HELPERS ---
def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _name_tokens(name: str) -> List[str]:
    n = _norm(name)
    n = re.sub(r"[^a-z\s\-']", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    toks = [t for t in n.split(" ") if t]
    return toks


def _is_high_risk_name(name: str) -> bool:
    toks = _name_tokens(name)
    if len(toks) <= 2:
        return True
    # Very short given name + common surname heuristic
    if len(toks) == 2 and (len(toks[0]) <= 3 or len(toks[1]) <= 3):
        return True
    return False


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip().lower()
    d = d.replace("https://doi.org/", "").replace("http://doi.org/", "")
    d = d.replace("doi:", "")
    d = d.strip()
    return d or None


def _contains_any(haystack: str, needles: set) -> bool:
    h = _norm(haystack)
    return any(n in h for n in needles)


def _extract_year_range(text: str) -> bool:
    """
    Detects patterns like 2019-2022 or 2019 – 2022 etc.
    """
    t = _norm(text)
    return bool(re.search(r"\b(19|20)\d{2}\s*[\-–]\s*(19|20)\d{2}\b", t))


def _safe_get(url: str, params: Optional[dict] = None, timeout: int = 30) -> Optional[requests.Response]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        return r
    except Exception:
        return None


# --- 1. STAFF DISCOVERY ---
def get_staff_list() -> List[str]:
    """
    Scrapes CURRENT people from demography.ox.ac.uk People page.

    The current markup uses:
      - each person card in .views-row
      - name in h3.paragraph-side-title
      - role/position in .field--name-field-position

    Falls back to older selectors if needed.
    """
    leads: List[str] = []

    r = _safe_get(PEOPLE_URL, timeout=30)
    if not r or r.status_code != 200:
        print(f"❌ Could not fetch People page: {PEOPLE_URL}")
        return leads

    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select(".view-content .views-row") or soup.select(".views-row")

    for card in cards:
        # Name
        name_el = card.select_one("h3.paragraph-side-title")
        if not name_el:
            # fallback older selector
            name_el = card.select_one("div.views-field-title span.field-content")

        name = _norm(name_el.get_text(" ", strip=True) if name_el else "")
        if not name:
            continue

        # Role / position (used to skip administrators and former members)
        pos_el = card.select_one(".field--name-field-position")
        position = _norm(pos_el.get_text(" ", strip=True) if pos_el else "")

        # Former / previously LCDS etc
        if position and (_contains_any(position, FORMER_KEYWORDS) or _extract_year_range(position)):
            continue

        # Admin / support filtering
        if position and _contains_any(position, ADMIN_KEYWORDS):
            continue

        # Skip obvious non-person entries
        if "contact" in name or "email" in name:
            continue

        leads.append(name.title())

    # Dedupe, stable order
    seen = set()
    out = []
    for n in leads:
        if n not in seen:
            out.append(n)
            seen.add(n)
    return out


# --- 2. ORCID RESOLUTION ---
def _crossref_orcid_candidates(name: str, rows: int = 30) -> Dict[str, dict]:
    """
    Returns candidate ORCIDs found in Crossref works search for the author name.
    Dictionary maps orcid -> evidence dict.
    """
    candidates: Dict[str, dict] = {}

    params = {
        "query.author": name,
        "rows": rows,
        "sort": "relevance",
        "order": "desc",
        "mailto": mailto,
    }
    r = _safe_get("https://api.crossref.org/works", params=params, timeout=30)
    if not r or r.status_code != 200:
        return candidates

    items = (r.json().get("message") or {}).get("items") or []
    for item in items:
        authors = item.get("author") or []
        for a in authors:
            orcid = a.get("ORCID")
            if not orcid:
                continue
            orcid = _norm(orcid).replace("https://orcid.org/", "")
            if not re.match(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$", orcid):
                continue

            affs = " ".join([x.get("name", "") for x in (a.get("affiliation") or [])])
            doi = normalize_doi(item.get("DOI"))
            title = (item.get("title") or [""])[0]
            journal = (item.get("container-title") or [""])[0]

            ev = candidates.setdefault(orcid, {"dois": set(), "aff_text": "", "journals": set(), "titles": set()})
            if doi:
                ev["dois"].add(doi)
            ev["aff_text"] += " " + (affs or "")
            if journal:
                ev["journals"].add(journal)
            if title:
                ev["titles"].add(title)

    return candidates


def _openalex_validate_orcid(orcid: str) -> Dict[str, bool]:
    """
    Validates ORCID using OpenAlex author record.
    Returns flags: oxford_match, lcds_match
    """
    flags = {"oxford_match": False, "lcds_match": False}

    # OpenAlex author by ORCID
    url = f"https://api.openalex.org/authors/orcid:{orcid}"
    r = _safe_get(url, timeout=20)
    if not r or r.status_code != 200:
        return flags

    data = r.json() or {}

    aff_text_parts = []
    lki = (data.get("last_known_institution") or {}).get("display_name") or ""
    if lki:
        aff_text_parts.append(lki)

    for a in (data.get("affiliations") or []):
        inst = (a.get("institution") or {}).get("display_name") or ""
        if inst:
            aff_text_parts.append(inst)

    display = data.get("display_name") or ""
    if display:
        aff_text_parts.append(display)

    aff_text = _norm(" ".join(aff_text_parts))

    if _contains_any(aff_text, OXFORD_TERMS):
        flags["oxford_match"] = True
    if _contains_any(aff_text, LCDS_TERMS):
        flags["lcds_match"] = True

    return flags


def _score_candidate(name: str, ev: dict, oa_flags: Dict[str, bool]) -> Tuple[int, Dict[str, bool]]:
    """
    Returns (score, evidence_flags)
    """
    evidence_flags = {
        "oxford_match": False,
        "lcds_match": False,
        "oxford_and_lcds": False,
        "domain_hint": False,
    }

    score = 0

    # Crossref affiliation string evidence if present
    aff_text = _norm(ev.get("aff_text", ""))

    cr_ox = _contains_any(aff_text, OXFORD_TERMS)
    cr_lcds = _contains_any(aff_text, LCDS_TERMS)

    ox = cr_ox or oa_flags.get("oxford_match", False)
    lcds = cr_lcds or oa_flags.get("lcds_match", False)

    evidence_flags["oxford_match"] = ox
    evidence_flags["lcds_match"] = lcds
    evidence_flags["oxford_and_lcds"] = ox and lcds

    # Strong: Oxford + LCDS
    if ox and lcds:
        score += 80
    elif ox:
        score += 45
    elif lcds:
        score += 25

    # Medium: domain hints from journals/titles
    blob = " ".join(list(ev.get("journals", set())) + list(ev.get("titles", set())))
    if _contains_any(blob, DOMAIN_TERMS):
        score += 15
        evidence_flags["domain_hint"] = True

    # Medium: repeated evidence across multiple works
    n_dois = len(ev.get("dois", set()))
    if n_dois >= 3:
        score += 15
    elif n_dois == 2:
        score += 8

    return score, evidence_flags


def get_orcid(name: str) -> Tuple[Optional[str], Dict[str, object]]:
    """
    Crossref is the main source. OpenAlex is used only to validate candidates and fill gaps.
    Returns (orcid or None, metadata dict).
    """
    meta: Dict[str, object] = {
        "confidence": 0,
        "status": "no_orcid",
        "evidence_flags": {},
        "supporting_dois": [],
        "source": "",
    }

    candidates = _crossref_orcid_candidates(name)
    if not candidates:
        meta["status"] = "no_orcid"
        return None, meta

    scored: List[Tuple[int, str, dict, dict]] = []
    for orcid, ev in candidates.items():
        oa_flags = _openalex_validate_orcid(orcid)
        score, flags = _score_candidate(name, ev, oa_flags)
        scored.append((score, orcid, ev, flags))

    scored.sort(reverse=True, key=lambda x: x[0])
    best_score, best_orcid, best_ev, best_flags = scored[0]

    # Determine if ambiguous
    second_score = scored[1][0] if len(scored) > 1 else -1
    ambiguous = (second_score >= best_score - 10) and (second_score > 0)

    high_risk = _is_high_risk_name(name)

    # Thresholds
    base_threshold = 70 if STRICT_DISAMBIGUATION else 55
    if high_risk or ambiguous:
        # For Wen Su type names, require Oxford + LCDS evidence
        if not best_flags.get("oxford_and_lcds", False):
            meta.update({
                "confidence": best_score,
                "status": "manual_review",
                "evidence_flags": best_flags,
                "supporting_dois": sorted(list(best_ev.get("dois", set())))[:10],
                "source": "crossref+openalex",
            })
            return None, meta
        base_threshold = max(base_threshold, 75)

    if best_score < base_threshold:
        meta.update({
            "confidence": best_score,
            "status": "manual_review",
            "evidence_flags": best_flags,
            "supporting_dois": sorted(list(best_ev.get("dois", set())))[:10],
            "source": "crossref+openalex",
        })
        return None, meta

    meta.update({
        "confidence": best_score,
        "status": "ok",
        "evidence_flags": best_flags,
        "supporting_dois": sorted(list(best_ev.get("dois", set())))[:10],
        "source": "crossref+openalex",
    })
    return best_orcid, meta


# --- 3. WORKS FETCHING ---
def fetch_works(name: str, orcid: str) -> List[dict]:
    """
    Fetch works for an ORCID.
    Crossref is primary.
    OpenAlex is used as a gap filler for items not returned by Crossref.
    """
    works_dict: Dict[str, dict] = {}
    if not orcid:
        return []

    # PHASE 1: Crossref
    try:
        cr_url = "https://api.crossref.org/works"
        cr_params = {
            "filter": f"orcid:{orcid},from-pub-date:{START_DATE}",
            "sort": "created",
            "order": "desc",
            "rows": 200,
            "mailto": mailto,
        }
        cr_r = _safe_get(cr_url, params=cr_params, timeout=30)

        if cr_r and cr_r.status_code == 200:
            for item in (cr_r.json().get("message") or {}).get("items") or []:
                d = item.get("published-online") or item.get("created") or item.get("published-print") or {}
                date_parts = d.get("date-parts") or []
                date_str = datetime.now().strftime("%Y-%m-%d")
                if date_parts and date_parts[0]:
                    p = date_parts[0]
                    if len(p) >= 3:
                        date_str = f"{p[0]:04d}-{p[1]:02d}-{p[2]:02d}"
                    elif len(p) == 2:
                        date_str = f"{p[0]:04d}-{p[1]:02d}-01"
                    elif len(p) == 1:
                        date_str = f"{p[0]:04d}-01-01"

                titles = item.get("title") or []
                title_str = str(titles[0]) if titles else "Untitled"
                journals = item.get("container-title") or []
                journal_str = str(journals[0]) if journals else "Preprint"

                doi_val = normalize_doi(item.get("DOI"))
                subtype = item.get("subtype")
                is_preprint = subtype == "preprint" or journal_str.lower() in {
                    "preprint", "medrxiv", "biorxiv", "socarxiv", "ssrn", "osf"
                }

                # Country enrichment via OpenAlex (lightweight)
                countries = ""
                if doi_val:
                    try:
                        time.sleep(0.05)
                        oa_r = _safe_get(
                            f"https://api.openalex.org/works/doi:https://doi.org/{doi_val}",
                            params={"select": "authorships"},
                            timeout=10,
                        )
                        if oa_r and oa_r.status_code == 200:
                            c_set = {
                                str(i.get("country_code"))
                                for a in (oa_r.json().get("authorships") or [])
                                for i in (a.get("institutions") or [])
                                if i.get("country_code")
                            }
                            countries = ",".join(sorted(c_set))
                    except Exception:
                        pass

                work_obj = {
                    "Date": date_str,
                    "Year": date_str.split("-")[0],
                    "LCDS Author": name,
                    "Title": title_str,
                    "Journal": journal_str,
                    "Type": "Preprint" if is_preprint else "Article",
                    "Citations": item.get("is-referenced-by-count", 0),
                    "DOI": f"https://doi.org/{doi_val}" if doi_val else "",
                    "Countries": countries,
                }

                dict_key = doi_val if doi_val else title_str.lower()
                works_dict[dict_key] = work_obj
    except Exception as e:
        print(f"[!] Crossref failed for {name}: {e}")

    # PHASE 2: OpenAlex gap filler
    try:
        oa_url = "https://api.openalex.org/works"
        oa_params = {
            "filter": f"author.orcid:https://orcid.org/{orcid},from_publication_date:{START_DATE}",
            "per-page": 200,
        }
        oa_r = _safe_get(oa_url, params=oa_params, timeout=30)

        if oa_r and oa_r.status_code == 200:
            for item in oa_r.json().get("results", []) or []:
                doi_val = normalize_doi(item.get("doi"))
                title_str = str(item.get("title") or "Untitled")
                title_key = title_str.lower()

                if (doi_val and doi_val in works_dict) or (title_key in works_dict):
                    continue

                date_str = item.get("publication_date") or f"{item.get('publication_year', 2020)}-01-01"
                journal_str = "Preprint"
                is_preprint = False

                loc = item.get("primary_location") or {}
                source = loc.get("source") or {}
                if source:
                    journal_str = source.get("display_name") or "Preprint"
                    if source.get("type") == "repository":
                        is_preprint = True

                c_set = {
                    str(i.get("country_code"))
                    for a in (item.get("authorships") or [])
                    for i in (a.get("institutions") or [])
                    if i.get("country_code")
                }

                work_obj = {
                    "Date": date_str,
                    "Year": date_str.split("-")[0],
                    "LCDS Author": name,
                    "Title": title_str,
                    "Journal": journal_str,
                    "Type": "Preprint" if is_preprint else "Article",
                    "Citations": item.get("cited_by_count", 0),
                    "DOI": f"https://doi.org/{doi_val}" if doi_val else "",
                    "Countries": ",".join(sorted(c_set)),
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
    if not staff:
        raise SystemExit("No staff discovered. Check PEOPLE_URL or parsing selectors.")

    if not os.path.exists(CSV_FILE):
        pd.DataFrame(
            columns=[
                "Date", "Year", "LCDS Author", "Title", "Journal",
                "Type", "Citations", "DOI", "Countries",
                "ORCID", "ORCID Confidence", "ORCID Status"
            ]
        ).to_csv(CSV_FILE, index=False, encoding="utf-8")

    print(f"[{datetime.now().time()}] Starting fetch for {len(staff)} researchers")

    for person in staff:
        print(f"\n[+] Researcher: {person}")
        time.sleep(0.4)

        orcid, meta = get_orcid(person)
        if not orcid:
            print(f"    ORCID: none ({meta.get('status')}, score {meta.get('confidence')})")
            continue

        print(f"    ORCID: {orcid} (score {meta.get('confidence')})")
        data = fetch_works(person, orcid)
        if not data:
            print("    No works found since START_DATE")
            continue

        df_new = pd.DataFrame(data)
        df_new["ORCID"] = f"https://orcid.org/{orcid}"
        df_new["ORCID Confidence"] = meta.get("confidence", 0)
        df_new["ORCID Status"] = meta.get("status", "ok")

        try:
            # Ensure file exists with header already. Append without header.
            df_new.to_csv(CSV_FILE, mode="a", header=False, index=False, encoding="utf-8")
            print(f"    Added {len(df_new)} works")
        except PermissionError:
            print("    FATAL: CSV is open elsewhere. Close it and rerun.")
            break

    # FINAL DEDUPLICATION
    try:
        df_final = pd.read_csv(CSV_FILE, encoding="utf-8")
        df_final.drop_duplicates(subset=["DOI", "Title", "LCDS Author"], inplace=True)
        df_final.to_csv(CSV_FILE, index=False, encoding="utf-8")
        print(f"\n✅ Done. Final unique records: {len(df_final)}")
    except Exception as e:
        print(f"\n[!] Could not deduplicate final CSV: {e}")
