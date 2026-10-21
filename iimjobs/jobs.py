"""/iimjobs/jobs/* — job search (the text search, a skill tag's feed or the
category / whole-board feed behind one endpoint, optionally read by the
site's AI query reader), jobs for women, job details, batch lookup and
similar jobs."""
from iimjobs import cache_config as ttl
from iimjobs import fetch, lookups, refdata
from iimjobs import parsers as P
from iimjobs import shared as S


def _workers():
    try:
        import config
        return int(config.IIMJOBS_WORKERS)
    except Exception:
        return 4


def _filters(query, skill_refs, category, location, industry, min_experience, max_experience, posted_within,
             interpreted=None):
    return {
        "query": query,
        "skills": skill_refs or None,
        "categories": lookups.category_refs(category),
        "locations": lookups.location_refs(location),
        "industries": lookups.industry_refs(industry),
        "min_experience": min_experience,
        "max_experience": max_experience,
        "posted_within_days": posted_within,
        "interpreted_query": interpreted,
    }


def search_params(query=None, skill_ids=None, category=None, location=None, industry=None, min_experience=None,
                  max_experience=None, posted_within=None, page=1, page_size=refdata.PAGE_SIZE):
    """Public params -> (the feed, the backend's own query). A text query goes
    to /search (every filter applies); a skill to the tag feed /keyword/ (it
    ignores categories); otherwise the category feed /category/ — all nine
    categories when none is given, which is the whole board, newest first."""
    common = {
        "page": max(1, page) - 1,
        "size": page_size,
        "loc": ",".join(str(i) for i in location) if location else None,
        "minexp": min_experience,
        "maxexp": max_experience,
        "posting": posted_within,
        "industry": ",".join(str(i) for i in industry) if industry else None,
    }
    if query:
        return "search", {"query": query, **common,
                          "categoryId": ",".join(str(c) for c in category) if category else None}
    if skill_ids:
        return "keyword", {"keywordId": ",".join(str(i) for i in skill_ids), **common}
    return "category", {"categoryId": ",".join(str(c) for c in (category or refdata.ALL_CATEGORY_IDS)), **common}


def _interpret(query):
    """The site's AI search reading of a sentence (cached a week)."""
    raw = fetch.shared_raw("extract_params", {"query": query.lower()}, lambda: fetch.extract_params(query),
                           ttl.INTERPRET_CACHE)
    return P.interpreted_query(raw)


def _with_details(cards):
    ids = [card["id"] for card in cards]
    outcomes = fetch.run_parallel([lambda i=i: details(i) for i in ids], _workers())
    out = []
    for card, (status, value) in zip(cards, outcomes):
        if status == "error" and not isinstance(value, fetch.IimjobsNotFound):
            print(f"iimjobs: details of job {card['id']} skipped: {value}")
        out.append(P.merge_card_details(card, value if status == "ok" else None))
    return out


def search(query=None, skill=None, category=None, location=None, industry=None, min_experience=None,
           max_experience=None, posted_within=None, smart_search=False, page=1, page_size=refdata.PAGE_SIZE,
           include_details=False):
    """One page of jobs. With `query` it is iimjobs' text search (title,
    company, skills); without, a skill tag's feed (`skill`) or the category
    feed (`category`, or every category = the whole board, newest first);
    location, industry, experience band and posting age narrow all three.
    `smart_search` lets the site's AI search read `query` as a sentence
    ("product manager fintech bangalore 5 years" -> the title "Product
    Manager" + location, industry and experience filters; explicit filters
    win). Cards from the text search are rich; skill / category cards are
    lighter (no recruiter, counts or industries) — include_details fetches
    every card's full record (one extra call per job, in parallel)."""
    if query and skill:
        raise ValueError("Use either `query` (iimjobs' text search) or `skill` (a skill tag's feed), not both: "
                         "the text search cannot be narrowed by skill tag.")
    if skill and category:
        raise ValueError("`skill` and `category` cannot be combined: iimjobs' skill feed ignores categories "
                         "(each skill belongs to one category already; see /iimjobs/skills).")
    if smart_search and not query:
        raise ValueError("`smart_search` reads `query`: pass one (e.g. 'product manager fintech bangalore 5 years').")
    if (page - 1) * page_size >= refdata.MAX_RESULTS_WINDOW:
        raise ValueError(f"iimjobs serves the first {refdata.MAX_RESULTS_WINDOW:,} results of a listing: "
                         f"page {page} at page_size {page_size} is past it; narrow the filters instead.")
    interpreted = None
    if smart_search:
        interpreted = _interpret(query)
        query = interpreted["query"] or " ".join(interpreted["job_titles"]) or query
        location = location or interpreted["location_ids"] or None
        industry = industry or interpreted["industry_values"] or None
        if min_experience is None and max_experience is None:
            min_experience, max_experience = interpreted["min_experience"], interpreted["max_experience"]
        posted_within = posted_within or interpreted["posted_within_days"]
    skill_ids, skill_refs = lookups.resolve_skill_ids(skill)
    kind, params = search_params(query, skill_ids, category, location, industry, min_experience, max_experience,
                                 posted_within, page, page_size)
    if kind == "search":
        raw = fetch.search(params, f"job search {query!r} p{page}")
    elif kind == "keyword":
        raw = fetch.keyword_feed(params, f"skill feed {skill_ids} p{page}")
    else:
        raw = fetch.category_feed(params, f"category feed {category or 'all'} p{page}")
    one_category = category[0] if kind == "category" and category and len(category) == 1 else None
    result = P.feed_result(raw, page, page_size, category_id=one_category)
    if include_details and result["jobs"]:
        result["jobs"] = _with_details(result["jobs"])
    result["filters"] = _filters(query, skill_refs, category, location, industry, min_experience, max_experience,
                                 posted_within, interpreted)
    return result


def for_women(location=None, category=None, min_experience=None, max_experience=None, page=1,
              page_size=refdata.PAGE_SIZE):
    """iimjobs' "Jobs for her": the jobs whose recruiters prefer women
    candidates (diversity hiring), newest first, with descriptions."""
    start = (page - 1) * page_size
    params = {
        "femaleFilter": 1,
        "start": start,
        "end": start + page_size,
        "minExp": min_experience,
        "maxExp": max_experience,
        "joblocationIds": ",".join(str(i) for i in location) if location else None,
        "categoryIds": ",".join(str(c) for c in category) if category else None,
    }
    result = P.offset_feed_result(fetch.women_feed(params, f"jobs for women p{page}"), page, page_size)
    result["filters"] = {"categories": lookups.category_refs(category), "locations": lookups.location_refs(location),
                         "min_experience": min_experience, "max_experience": max_experience}
    return result


# ---- details ------------------------------------------------------------------------------------------------

def _company_page(raw):
    """The hiring company's own page ({slug, link}) for a job record, cached:
    /company-slug?id= by the company id, the page live only when it has an
    AmbitionBox profile (the site 404s the rest)."""
    company = P.job_company(raw)
    if not company or not company.get("id"):
        return None
    from iimjobs import companies
    return companies.page_of(company["id"])


def details(job):
    """The full ad: description (HTML + text), skills with mandatory flags,
    experience band, salary (when disclosed), locations, industries,
    diversity flags and programme, the application / view / recruiter-
    action counts, the recruiter, and the company with its own page and
    full AmbitionBox profile. 404 when the site has no such job; removed
    ads still come back with is_active false."""
    raw = fetch.job_detail(job)
    try:
        page = _company_page(raw)
    except fetch.IimjobsUpstreamError as e:
        print(f"iimjobs: company page of job {job} skipped: {e}")
        page = None
    result = P.job_details(raw, company_page=page)
    if result is None:
        raise fetch.IimjobsNotFound(f"iimjobs has no job with the id {job}")
    return result


def batch(jobs):
    """Up to MAX_BATCH jobs by id / link, fetched in parallel. Jobs the site
    does not have are listed under `errors` instead of failing the call."""
    outcomes = fetch.run_parallel([lambda j=j: details(j) for j in jobs], _workers())
    out, errors = [], {}
    for job_id, (status, value) in zip(jobs, outcomes):
        if status == "ok":
            out.append(value)
        elif isinstance(value, fetch.IimjobsNotFound):
            errors[str(job_id)] = "not found"
        else:
            raise value
    return {"jobs": out, "count": len(out), "errors": errors or None}


def similar(job, limit=20):
    """The jobs iimjobs lists as similar to `job` (its skill tags, category
    and experience band), best match first."""
    record = fetch.job_detail(job)
    tag_ids = [t.get("id") for t in (record.get("tags") or []) if isinstance(t, dict) and t.get("id") is not None]
    rows = fetch.similar_jobs(record.get("id"), tag_ids, record.get("categoryId"), S.to_int(record.get("min")),
                              size=min(refdata.SIMILAR_LIMIT, limit + 1))
    jobs = [P.job_card(r) for r in rows if isinstance(r, dict) and r.get("id") != record.get("id")][:limit]
    head = P.job_card(record)
    return {"job": {"id": head["id"], "title": head["title"], "link": head["link"]}, "jobs": jobs, "count": len(jobs)}
