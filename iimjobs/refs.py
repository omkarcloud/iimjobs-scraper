"""iimjobs input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values (so validated params stay usable
as a response-cache key) and raises ValueError with a user-facing message.

  job        1740408 | https://www.iimjobs.com/j/piramal-product-manager-1740408
             | piramal-product-manager-1740408                          -> 1740408
  company    30 (the company id job cards carry) | https://www.iimjobs.com/kpmg-careers
             | kpmg-careers | piramal-pharma | KPMG (a name, looked up at call time)
             -> {"id": 30, "slug": None, "name": None} / {"id": None, "slug": "kpmg", …}
              / {"id": None, "slug": None, "name": "KPMG"}
  recruiter  65 | https://www.iimjobs.com/r/65-sibal-vertexcorp-com | 65-sibal   -> 65
  course     2930 | https://www.iimjobs.com/course/IIM-Kashipur-%7C-…-2930           -> 2930
  location   Bangalore | bengaluru | 3 | remote | Delhi NCR | metros | Pune, Mumbai
             -> the picker ids, umbrella entries expanded
  category   banking-finance | banking-finance-jobs | 13 | Banking & Finance | finance (comma list)
  industry   FinTech | 2 | t-1 | Banking / Financial Services / Broking | pharma (comma list)
             -> the backend's values ['t-1', '2', …] (refdata.INDUSTRIES / TRENDING_INDUSTRIES)
  skill      sales | 155 | Brand Management (comma list) -> names / ids matched against
             the live tag table at call time (lookups.resolve_skill_ids).
"""
import re
from urllib.parse import unquote, urlparse

from iimjobs import refdata

_HOST_RE = re.compile(r"(?:^|\.)iimjobs\.(?:com|tech)$")
_NAME_BAD = re.compile(r"[/?#\\<>\"]")


def _parse_url(value):
    """-> (host, path) when value is an iimjobs URL or host path, None when it
    is plain text. Raises ValueError for another site's URL."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if not _HOST_RE.search(head):
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not _HOST_RE.search(host):
        raise ValueError("Must be an iimjobs.com link.")
    return host, unquote(parsed.path)


def _split(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _trailing_id(path, hint):
    match = re.search(r"(?:^|/|-)(\d+)/?$", path)
    if not match:
        raise ValueError(hint)
    return int(match.group(1))


# ---- jobs -------------------------------------------------------------------------------------------

JOB_HINT = ("Must be an iimjobs job id (digits, e.g. 1740408) or a job link "
            "(https://www.iimjobs.com/j/piramal-product-manager-1740408).")


def resolve_job(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return int(raw)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    path = url[1] if url else raw.split("?", 1)[0].split("#", 1)[0]
    if url and not re.search(r"(?:^|/)j/", path):
        raise ValueError(JOB_HINT)
    if not url and "/" in path.strip("/"):
        raise ValueError(JOB_HINT)
    return _trailing_id(path, JOB_HINT)


def resolve_jobs(value, limit=refdata.MAX_BATCH):
    """'1740408, https://www.iimjobs.com/j/x-1740555' -> [1740408, 1740555] (deduped, 1..limit)."""
    out = []
    for item in _split(value):
        job_id = resolve_job(item)
        if job_id not in out:
            out.append(job_id)
    if not out:
        raise ValueError("Must list at least one job id or link (comma-separated).")
    if len(out) > limit:
        raise ValueError(f"At most {limit} jobs.")
    return out


# ---- companies ----------------------------------------------------------------------------------------

COMPANY_HINT = ("Must be a company id (digits, the `company.id` of a job, e.g. 30), a company page link or "
                "slug (https://www.iimjobs.com/kpmg-careers, kpmg) or a company name (KPMG).")

_RESERVED_PATHS = {"j", "k", "c", "r", "search", "blog", "company", "jobs", "course", "courses", "learning",
                   "sitemap", "contact", "terms", "privacy", "grievances", "faq", "aboutus", "refund",
                   "downloadapp", "jobfeed", "registration", "login"}


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    if raw.isdigit():
        if int(raw) <= 0:
            raise ValueError(COMPANY_HINT)
        return {"id": int(raw), "slug": None, "name": None}
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if url:
        match = re.match(r"^/(?:company/)?([a-z0-9][a-z0-9-]*?)(?:-careers)?/?$", url[1].lower())
        if not match or match.group(1) in _RESERVED_PATHS:
            raise ValueError("Links must be company pages (https://www.iimjobs.com/<company>-careers).")
        return {"id": None, "slug": match.group(1), "name": None}
    # a slug carries a hyphen (piramal-pharma) or the -careers suffix; a bare
    # word (kpmg) is read as a name and matched at call time
    match = re.fullmatch(r"([a-z0-9][a-z0-9-]*?)(?:-careers)?/?", raw.lower())
    if match and " " not in raw and ("-" in match.group(1) or raw.lower().endswith("-careers")):
        return {"id": None, "slug": match.group(1), "name": None}
    name = " ".join(raw.split())
    if _NAME_BAD.search(name) or len(name) > 150:
        raise ValueError(COMPANY_HINT)
    return {"id": None, "slug": None, "name": name}


# ---- recruiters / courses --------------------------------------------------------------------------------

RECRUITER_HINT = ("Must be an iimjobs recruiter id (digits, e.g. 65) or a recruiter profile link "
                  "(https://www.iimjobs.com/r/65-sibal-vertexcorp-com).")


def resolve_recruiter(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return int(raw)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(RECRUITER_HINT)
    path = url[1] if url else raw
    if url and not re.search(r"(?:^|/)r/", path):
        raise ValueError(RECRUITER_HINT)
    match = re.search(r"(?:^|/)(?:r/)?(\d+)(?:-[^/]*)?/?$", path)
    if match:
        return int(match.group(1))
    raise ValueError(RECRUITER_HINT)


COURSE_HINT = ("Must be an iimjobs course id (digits, e.g. 2930) or a course link "
               "(https://www.iimjobs.com/course/IIM-Kashipur-%7C-Executive-Program-Financial-Analytics-%26-AI-2930).")


def resolve_course(value):
    raw = (value or "").strip()
    if raw.isdigit():
        return int(raw)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COURSE_HINT)
    if not url or not re.search(r"(?:^|/)course/", url[1]):
        raise ValueError(COURSE_HINT)
    return _trailing_id(url[1], COURSE_HINT)


# ---- locations ----------------------------------------------------------------------------------------------

_LOCATION_ALIASES = {
    "bengaluru": 3, "bengalore": 3, "blr": 3, "bombay": 2, "madras": 6, "calcutta": 5, "gurgaon": 37, "gurugram": 37,
    "ncr": 1, "delhi-ncr": 1, "delhi/ncr": 1, "delhi / ncr": 1, "new delhi": 36, "kochi": 70, "cochin": 70,
    "vizag": 78, "visakhapatnam": 78, "trivandrum": 75, "thiruvananthapuram": 75, "mysuru": 73, "mysore": 73,
    "pondicherry": 85, "puducherry": 85, "vadodara": 56, "baroda": 56, "poona": 7,
    "remote": refdata.REMOTE_ID, "work from home": refdata.REMOTE_ID, "wfh": refdata.REMOTE_ID,
    "anywhere": refdata.ANYWHERE_IN_INDIA_ID, "india": refdata.ANYWHERE_IN_INDIA_ID,
    "anywhere in india": refdata.ANYWHERE_IN_INDIA_ID, "pan india": refdata.ANYWHERE_IN_INDIA_ID,
    "international": refdata.OVERSEAS_ID, "overseas": refdata.OVERSEAS_ID, "abroad": refdata.OVERSEAS_ID,
    "metro": refdata.METROS_ID, "metros": refdata.METROS_ID, "metro cities": refdata.METROS_ID,
}

_INDEX = None

def location_index():
    """lower-cased name / id / alias -> location id (cached)."""
    global _INDEX
    if _INDEX is None:
        index = {}
        for loc_id, name in refdata.LOCATIONS.items():
            index[str(loc_id)] = loc_id
            index[" ".join(name.lower().split())] = loc_id
            # 'Gurgaon/Gurugram', 'Cochin/Kochi', 'Vishakhapatnam/Vizag' -> each half
            for part in re.split(r"\s*/\s*", name.lower()):
                part = " ".join(part.split())
                if part and part not in index:
                    index[part] = loc_id
        for alias, loc_id in _LOCATION_ALIASES.items():
            if loc_id in refdata.LOCATIONS:
                index[alias] = loc_id
        _INDEX = index
    return _INDEX


LOCATION_HINT = ("Must be a city, state, country or region as iimjobs lists it (Mumbai, Bangalore, Delhi NCR, "
                 "Gurgaon, Maharashtra, Remote, Metros, Anywhere in India, Overseas) or its id; "
                 "see /iimjobs/locations.")


def resolve_locations(value, limit=10):
    """'Bangalore, bengaluru, remote, metros' -> [3, 132, <the metro ids>]
    (the picker ids the backend accepts, umbrella entries expanded, deduped)."""
    items = _split(value)
    if len(items) > limit:
        raise ValueError(f"At most {limit} locations.")
    index = location_index()
    out = []
    for item in items:
        loc_id = index.get(" ".join(item.lower().split()))
        if loc_id is None:
            raise ValueError(f"'{item}' is not a location iimjobs knows. " + LOCATION_HINT)
        for member in [loc_id] + list(refdata.LOCATION_GROUPS.get(loc_id, [])):
            if member not in out:
                out.append(member)
    return out or None


# ---- categories ---------------------------------------------------------------------------------------------

def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower().replace("&", " and ")).strip()


def _category_index():
    index = {}
    for cid, (slug, name) in refdata.CATEGORIES.items():
        for key in (str(cid), slug, slug[:-len("-jobs")], name):
            index[_norm(key)] = cid
    for alias, cid in refdata.CATEGORY_ALIASES.items():
        index.setdefault(_norm(alias), cid)
    return index


CATEGORY_HINT = "see /iimjobs/categories"


def resolve_categories(value, limit=10):
    """'banking-finance, Sales & Marketing, 15, hr' -> [13, 14, 15, 17]."""
    index = _category_index()
    out = []
    for item in _split(value):
        cid = index.get(_norm(item))
        if cid is None:
            raise ValueError(f"'{item}' is not a job category id, slug or name; {CATEGORY_HINT}.")
        if cid not in out:
            out.append(cid)
    if len(out) > limit:
        raise ValueError(f"At most {limit} categories.")
    return out or None


# ---- industries ---------------------------------------------------------------------------------------------

def _compact(value):
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _industry_names():
    names = {f"t-{i}": n for i, n in refdata.TRENDING_INDUSTRIES.items()}
    names.update({str(i): n for i, n in refdata.INDUSTRIES.items()})
    return names


INDUSTRY_HINT = "see /iimjobs/industries"


def resolve_industries(value, limit=10):
    """'FinTech, 2, t-3, pharma' -> ['t-1', '2', 't-3', '28']: the backend's
    `industry` values — a regular industry's id, a trending industry's
    't-<id>'. Names match the industry table exactly (punctuation and case
    ignored: 'edtech' = 'Ed-Tech'), else by a unique partial match
    ('pharma' -> 'Biotechnology & Pharmaceuticals')."""
    names = _industry_names()
    by_compact = {}
    for key, name in names.items():
        by_compact.setdefault(_compact(name), key)
    out = []
    for item in _split(value):
        low = " ".join(item.lower().split())
        if low.isdigit() or re.fullmatch(r"t-\d+", low):
            key = low                                   # an id: passed through (the table may have grown)
        else:
            compact = _compact(low)
            key = by_compact.get(compact)
            if key is None and len(compact) >= 3:
                hits = sorted({k for c, k in by_compact.items() if compact in c})
                if len(hits) == 1:
                    key = hits[0]
                elif hits:
                    options = ", ".join(names[h] for h in hits[:6])
                    raise ValueError(f"'{item}' matches several industries ({options}); {INDUSTRY_HINT}.")
            if key is None:
                raise ValueError(f"'{item}' is not an industry id or name; {INDUSTRY_HINT}.")
        if key not in out:
            out.append(key)
    if len(out) > limit:
        raise ValueError(f"At most {limit} industries.")
    return out or None


# ---- skills ------------------------------------------------------------------------------------------------------

def resolve_skills(value, limit=10):
    """'Python, 203, django' -> ['python', 203, 'django']: ids stay ints,
    names are lower-cased and matched against the live tag table at call
    time (lookups.resolve_skill_ids), where an unknown name is a 400."""
    out = []
    for item in _split(value):
        key = item.strip()
        if key.isdigit():
            key = int(key)
        else:
            key = " ".join(key.lower().split())
            if _NAME_BAD.search(key) or len(key) > 80:
                raise ValueError(f"'{item}' is not a skill name or id.")
        if key not in out:
            out.append(key)
    if len(out) > limit:
        raise ValueError(f"At most {limit} skills.")
    return out or None
