"""/iimjobs/companies/* — company search (the site's company directory, or a
name looked up in the directory, the page records and the job search),
company pages (page record + AmbitionBox profile + what its open jobs say)
and a company's open jobs.

A company is keyed by the id every job's recruiter block carries (the
site's "centralised company id"): /top-jobs?cid= lists its jobs,
/company-slug?id= names its page. A page slug maps back through
/company-id-slug?slug= (or, for the AmbitionBox-only pages the job ads
link to, the profile's own id). The site serves /<slug>-careers only for
companies with an AmbitionBox profile — `link` is null for the rest."""
import re

from iimjobs import cache_config as ttl
from iimjobs import fetch, refdata
from iimjobs import parsers as P
from iimjobs import shared as S
from iimjobs.shared import as_dict


def _workers():
    try:
        import config
        return int(config.IIMJOBS_WORKERS)
    except Exception:
        return 4


# ---- cached page lookups ----------------------------------------------------------------------------------

def _record_by_id(company_id):
    return fetch.shared_raw("company_slug", {"id": company_id}, lambda: fetch.company_slug(company_id),
                            ttl.COMPANY_PAGE_CACHE)


def _record_by_slug(slug):
    return fetch.shared_raw("company_record", {"slug": slug}, lambda: fetch.company_record(slug),
                            ttl.COMPANY_PAGE_CACHE)


def _ambitionbox(slug):
    if not slug:
        return {}
    return fetch.shared_raw("company_data", {"slug": slug}, lambda: fetch.company_data(slug), ttl.COMPANY_CACHE)


def page_of(company_id):
    """{slug, link} of a company id's own page (link null when the site has
    no live page for it); None when the company has no page record."""
    record = _record_by_id(company_id)
    slug = S.text(as_dict(record).get("slug"))
    if not slug:
        return None
    return {"slug": slug, "link": S.company_link(slug) if _ambitionbox(slug) else None}


# ---- resolving a `company` param ---------------------------------------------------------------------------

def _words(value):
    return [w for w in re.split(r"[^a-z0-9]+", (value or "").lower()) if w]


def _matches(name, query_words):
    haystack = " ".join(_words(name))
    return bool(query_words) and all(w in haystack for w in query_words)


def _job_groups(query, limit=100):
    """Companies hiring under `query` in the text search: job cards grouped by
    company id, kept when the employer's name carries every query word."""
    words = _words(query)
    try:
        raw = fetch.search({"query": query, "page": 0, "size": limit}, f"companies hiring {query!r}")
    except fetch.IimjobsNotFound:
        return []
    groups = {}
    for card in (P.job_card(c) for c in raw.get("data") or [] if isinstance(c, dict)):
        company = card.get("company") or {}
        if company.get("id") and (_matches(company.get("name"), words) or _matches(company.get("domain"), words)):
            groups.setdefault(company["id"], []).append(card)
    return sorted(groups.values(), key=len, reverse=True)


def _candidates(query):
    """Company cards matching a name: the page whose slug is the name, the
    directory's hits, and the employers the job search finds, merged by id
    (exact name / slug first)."""
    slug = S.slugify(query)
    outcomes = fetch.run_parallel([lambda: _record_by_slug(slug) if slug else {},
                                   lambda: fetch.company_search(query),
                                   lambda: _job_groups(query)], 3)
    for status, value in outcomes:
        if status == "error" and not isinstance(value, fetch.IimjobsNotFound):
            raise value
    record, directory, groups = [v if s == "ok" else None for s, v in outcomes]
    out, index = [], {}

    def add(card):
        key = card.get("id") or card.get("slug")
        if not key:
            return
        if key in index:                 # the same company found twice: fill the gaps
            out[index[key]] = P.merge_company_cards(out[index[key]], card)
        else:
            index[key] = len(out)
            out.append(card)
    record = as_dict(record)
    if record.get("centralisedCompanyId"):
        add(P.company_card(record))
    words = _words(query)
    for doc in as_dict(directory).get("docs") or []:
        card = P.company_card(doc)
        if _matches(" ".join(filter(None, [card["name"], card["slug"]])), words):
            add(card)
    for group in groups or []:
        add(P.company_from_jobs(group))
    key = " ".join(words)
    out.sort(key=lambda c: 0 if (" ".join(_words(c.get("name"))) == key or c.get("slug") == slug) else 1)
    return out


def _fill_pages(cards):
    """Slugs / links for the cards found through the job search (cached)."""
    missing = [c for c in cards if c.get("id") and not c.get("slug")]
    outcomes = fetch.run_parallel([lambda c=c: page_of(c["id"]) for c in missing], _workers())
    for card, (status, value) in zip(missing, outcomes):
        if status == "ok" and value:
            card["slug"], card["link"] = value["slug"], value["link"]
    return cards


def resolve(company):
    """A validated `company` ({id} | {slug} | {name}) -> (company id, page
    slug, page record). IimjobsNotFound when nothing matches."""
    if company.get("id"):
        record = as_dict(_record_by_id(company["id"]))
        return company["id"], S.text(record.get("slug")), record
    if company.get("slug"):
        slug = company["slug"]
        record = as_dict(_record_by_slug(slug))
        company_id = S.to_int(record.get("centralisedCompanyId"))
        if not company_id:          # an AmbitionBox-only page (the kind job ads link to)
            company_id = S.to_int(as_dict(_ambitionbox(slug)).get("centralisedCompanyId"))
        if not company_id and not record:
            raise fetch.IimjobsNotFound(f"iimjobs has no company page {slug!r}")
        return company_id, slug, record
    name = company["name"]
    hits = fetch.shared_raw("company_by_name", {"name": name.lower()}, lambda: _candidates(name)[:1],
                            ttl.COMPANY_PAGE_CACHE)
    if not hits:
        raise fetch.IimjobsNotFound(f"iimjobs has no company named {name!r}")
    head = hits[0]
    if head.get("slug"):
        return head.get("id"), head["slug"], as_dict(_record_by_slug(head["slug"]))
    record = as_dict(_record_by_id(head["id"])) if head.get("id") else {}
    return head.get("id"), S.text(record.get("slug")), record


# ---- endpoints ----------------------------------------------------------------------------------------------

def search(query=None, page=1):
    """With `query`: the companies whose name matches (the directory, the
    company pages and the employers hiring in the job search), one page.
    Without: the company directory, 50 a page."""
    if query:
        cards = _fill_pages(_candidates(query))
        return {"companies": cards, "filters": {"query": query},
                "pagination": {"page": 1, "items_per_page": len(cards), "total_pages": 1 if cards else 0,
                               "total_count": len(cards)}}
    result = P.company_list_result(fetch.company_list(page - 1), page, refdata.COMPANY_LIST_PAGE_SIZE)
    result["filters"] = {"query": None}
    return result


def _jobs_page(company_id, page):
    if not company_id:
        return {"jobs": [], "hasMore": False, "count": 0, "count1Year": 0}
    return fetch.company_jobs(company_id, page - 1)


def details(company, include_jobs=True):
    """The company page: id, name, page slug and link, logo, domains,
    sectors, open-job count, the showcase and diversity programme, the full
    AmbitionBox profile (about, size, rating, reviews, benefits, ratings by
    role); with include_jobs the first 15 of its open jobs."""
    company_id, slug, record = resolve(company)
    outcomes = fetch.run_parallel([lambda: _ambitionbox(slug), lambda: _jobs_page(company_id, 1)], 2)
    for status, value in outcomes:
        if status == "error":
            raise value
    ambitionbox, jobs = (v for _, v in outcomes)
    if not record and not ambitionbox and not jobs["jobs"]:
        raise fetch.IimjobsNotFound(f"iimjobs has no company {company_id or slug!r}")
    out = P.company_profile(company_id, slug, record, ambitionbox, jobs["jobs"], jobs_count=S.count(jobs["count"]))
    out["jobs"] = P.company_jobs_result(jobs, 1)["jobs"] if include_jobs else None
    return out


def open_jobs(company, page=1):
    """One page (15) of a company's open jobs — the full records, descriptions included."""
    company_id, slug, record = resolve(company)
    if not company_id:
        raise fetch.IimjobsNotFound(f"iimjobs lists no jobs for the company page {slug!r}")
    raw = _jobs_page(company_id, page)
    result = P.company_jobs_result(raw, page)
    head = P.company_profile(company_id, slug, record, _ambitionbox(slug), raw["jobs"],
                             jobs_count=result["pagination"]["total_count"])
    result["company"] = {"id": head["id"], "name": head["name"], "slug": head["slug"], "link": head["link"],
                         "logo": head["logo"], "jobs_count": head["jobs_count"]}
    return result
