"""iimjobs.com transport: plain curl_cffi, no browser, validated 2026-10-19
from a direct India egress with no cookies and no login.

The site is a Next.js shell; every listing comes from its job service at
gladiator.iimjobs.com/job (the same codebase as hirist.tech's), which
answers an anonymous client carrying the bundle's `version: 2` header, and
iimjobs Learning's course service at lng-api.iimjobs.com. Surfaces:

  search(params)              /search?query=&page=&size=&loc=&minexp=&maxexp=&posting=
                              &categoryId=&industry= — the text search (title, company,
                              skills); rich cards. An empty query is a 404 upstream.
  keyword_feed(params)        /keyword/?keywordId=&… — a skill tag's feed (comma = OR);
                              slim cards; ignores categoryId.
  category_feed(params)       /category/?categoryId=&… — a category's feed (comma = OR;
                              all nine = the whole board, newest first); slim cards.
  women_feed(params)          /female-jobs?femaleFilter=1&start=&end=&minExp=&maxExp=
                              &joblocationIds=&categoryIds= — "Jobs for her"; rich cards
                              with descriptions.
  job_detail(id)              /detail?jobcode= — the full ad (removed ads still answer).
  similar_jobs(…)             /similarjobs?id=&tags=&cat=&exp=&size= — up to 100.
  tags() / tag_info(slug)     /tags (every skill tag by category with its live job count),
                              /taginfo?slug=.
  suggest(query)              /search/keyword?query= — the search box.
  industries()                /data/industry — the industry filter's vocabulary.
  extract_params(query)       POST /extract-param — the site's AI search: a sentence ->
                              title / locations / industries / experience / skills.
  company_list(page)          /company-list?page= — the company directory, 50 a page.
  company_search(keyword)     /company-list/search?keyword= — the directory by name.
  company_record(slug)        /company-id-slug?slug= — a company page's record (ids,
                              names, domains); {} for an unknown slug.
  company_slug(company_id)    /company-slug?id= — the page record of a company id.
  company_data(slug)          /company-data?slug= — the AmbitionBox profile ({} if none).
  company_jobs(id, page)      /top-jobs?cid=&page= — a company's open jobs, 15 a page,
                              `count` the total (keyed by the centralised company id
                              every job's recruiter block carries).
  company_slugs()             /companies/slugs — every company page slug with its name.
  recruiter(id)               /data/recruiter?id= (an unknown id is a 500 upstream).
  recruiter_jobs(id, page)    /recruiterfeed/?recruiterId=&page= — 20 a page.
  courses(category_id)        lng-api /v2/courses/<catId> (0 = every course; one page).
  course_detail(id)           lng-api /v2/course/0/user/<id>/detail + /v2/course/<id>.

Logged out, /detail masks applyCount / hits / recruiterName as '*****'
(the rich feeds still carry them). /jobfeed and /insights need a login.

Egress: direct by default (config.IIMJOBS_PROXY_COUNTRY None); no rate
limit or challenge was seen. A 429 / 403 / 5xx is retried on a fresh
sticky residential exit (config.iimjobs_proxy(fallback=True)). The
patchright click-through (indeed/fetch.py _browser_page) is the
escalation if a challenge ever appears — not built while plain HTTP works.

The session pool, challenge markers, memo and parallel runner work as in
hirist/fetch.py (same service, same behaviour); the error types and retry
policy are iimjobs' own (config.IIMJOBS_*).

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  IimjobsUpstreamError  transport failure / 5xx / unexpected body — retryable
  IimjobsBlocked        429 / 403 / challenge                     — retryable on a new exit
  IimjobsBadRequest     the site rejected the params (400)        — never retried
  IimjobsNotFound       no such job / company / recruiter / course — never retried
"""
import json
import os
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from iimjobs import refdata

IMPERSONATE = "chrome"
TIMEOUT = (10, 60)            # (connect, read) — /tags and /companies/slugs are big

HEADERS = {"accept": "application/json, text/plain, */*", "accept-language": "en-US,en;q=0.9",
           "origin": refdata.BASE_URL, "referer": refdata.BASE_URL + "/"}
JOB_HEADERS = {**HEADERS, "version": "2"}
CF_MARKERS = ("just a moment", "challenge-error-text", "cf-chl", "challenge-platform", "attention required")


class IimjobsUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class IimjobsBlocked(IimjobsUpstreamError, Blocked):
    """429 / 403 / challenge — retryable on a fresh exit."""


class IimjobsBadRequest(BadRequest):
    """The site rejected the params — never retried."""


class IimjobsNotFound(NotFound):
    """No such job / company / recruiter / course — never retried."""


def dump_debug(name, text):
    """Write a raw response to $IIMJOBS_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("IIMJOBS_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- curl sessions (per thread, keyed by exit) ---------------------------------------------------

_local = threading.local()

def _sessions():
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = OrderedDict()
    return store

def _session(key, proxy):
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess

def _drop_session(key):
    sess = _sessions().pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def is_challenged(status, headers, text):
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)

def _error_message(body, text):
    """The backend's error body is {"error": {"statusCode", "name", "message"}}."""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        return f"{err.get('name') or 'error'}: {err.get('message') or ''}".strip(": ")
    return (text or "")[:200]


def _attempts(label, send):
    """Run send(session) under the retry policy: IimjobsUpstreamError (incl.
    Blocked) retries on a fresh exit up to config.IIMJOBS_MAX_ATTEMPTS
    times; BadRequest / NotFound surface at once."""
    attempts = max(1, int(config.IIMJOBS_MAX_ATTEMPTS))
    last = None
    for attempt in range(1, attempts + 1):
        proxy = config.iimjobs_proxy(fallback=attempt > 1)
        key = f"iimjobs:{attempt if proxy else 0}:{proxy or 'direct'}"
        sess = _session(key, proxy)
        try:
            return send(sess)
        except (IimjobsBadRequest, IimjobsNotFound):
            raise
        except IimjobsUpstreamError as e:
            last = e
        except Exception as e:
            last = IimjobsUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
        _drop_session(key)
        print(f"iimjobs: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(1.0 * attempt)
    raise last


def _classify(resp, label, missing_on_500=False):
    """Raise the failure a response represents, else return its JSON.
    `missing_on_500`: the endpoint answers a bare 500 for an unknown id."""
    status = resp.status_code
    text = resp.text or ""
    if is_challenged(status, dict(resp.headers), text):
        dump_debug("challenged", text)
        raise IimjobsBlocked(f"challenge (HTTP {status}) on {label}")
    if status in (403, 429):
        raise IimjobsBlocked(f"HTTP {status} on {label}")
    try:
        body = json.loads(text) if text else None
    except ValueError:
        body = None
    if status in (404, 410):
        raise IimjobsNotFound(f"iimjobs has no record for {label}")
    if status == 400:
        raise IimjobsBadRequest(f"iimjobs rejected the request on {label}: {_error_message(body, text)}")
    if status == 500 and missing_on_500 and _error_message(body, text) == "error: Internal Server Error":
        raise IimjobsNotFound(f"iimjobs has no record for {label}")
    if status >= 500:
        raise IimjobsUpstreamError(f"HTTP {status} on {label}: {_error_message(body, text)}")
    if status != 200:
        raise IimjobsUpstreamError(f"HTTP {status} on {label}")
    if body is None:
        dump_debug("non_json", text)
        raise IimjobsUpstreamError(f"non-JSON answer on {label}")
    # the job service answers 200 with an {"error": {...}} body for some failures
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("statusCode")
        name = str(body["error"].get("name") or "")
        if code == 404 or "NOT_FOUND" in name:
            raise IimjobsNotFound(f"iimjobs has no record for {label}")
        if code == 401:
            raise IimjobsBadRequest(f"iimjobs needs a login for {label}")
        if code == 400:
            raise IimjobsBadRequest(f"iimjobs rejected the request on {label}: {_error_message(body, text)}")
        raise IimjobsUpstreamError(f"{_error_message(body, text)} on {label}")
    return body


def _request(method, url, label, expect, headers, json_body=None, missing_on_500=False):
    def send(sess):
        if method == "POST":
            resp = sess.post(url, json=json_body, headers=headers, timeout=TIMEOUT)
        else:
            resp = sess.get(url, headers=headers, timeout=TIMEOUT)
        body = _classify(resp, label, missing_on_500)
        if expect is not None and not isinstance(body, expect):
            dump_debug("unexpected", resp.text)
            raise IimjobsUpstreamError(f"unexpected payload on {label}")
        return body
    return _attempts(label, send)


def _url(base, path, params):
    query = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    return f"{base}{path}" + (f"?{urlencode(query, doseq=True)}" if query else "")


def api_get(path, params=None, label=None, expect=dict):
    """GET one endpoint of the job service -> its parsed body (`expect` = the body type)."""
    return _request("GET", _url(refdata.API_URL, path, params), label or path, expect, JOB_HEADERS)


def learning_get(path, params=None, label=None, expect=dict):
    """GET one endpoint of iimjobs Learning's course service."""
    return _request("GET", _url(refdata.LEARNING_API_URL, path, params), label or path, expect, HEADERS)


def _feed(path, params, label):
    body = api_get(path, params, label)
    if not isinstance(body.get("data"), list):
        dump_debug("feed", json.dumps(body)[:20000])
        raise IimjobsUpstreamError(f"unexpected feed payload on {label}")
    return body


# ---- jobs ------------------------------------------------------------------------------------------

def search(params, label="job search"):
    """GET /search (the backend's own param names) -> {data, page, limit,
    count, totalJobs, count1Year, totalPages, hasMore}."""
    return _feed("/search", params, label)


def keyword_feed(params, label="skill feed"):
    return _feed("/keyword/", params, label)


def category_feed(params, label="category feed"):
    return _feed("/category/", params, label)


def women_feed(params, label="jobs for women"):
    """GET /female-jobs (femaleFilter=1: the jobs whose recruiters prefer
    women; start / end are offsets) -> {"jobs": [...], "count": total, "hasMore"}."""
    body = api_get("/female-jobs", params, label)
    data = body.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        dump_debug("women_feed", json.dumps(body)[:20000])
        raise IimjobsUpstreamError(f"unexpected payload on {label}")
    return data


def job_detail(job_id):
    """The full job record; IimjobsNotFound when the id does not exist
    (removed ads still answer, with hasExpired / permanentlyRemoved true)."""
    body = api_get("/detail", {"jobcode": job_id}, label=f"job {job_id}")
    data = body.get("data")
    if not isinstance(data, dict) or data.get("id") is None:
        raise IimjobsNotFound(f"iimjobs has no job with the id {job_id}")
    return data


def similar_jobs(job_id, tag_ids, category_id=None, min_experience=None, size=refdata.SIMILAR_LIMIT):
    """The JD page's "similar jobs" (needs the job's tag ids; none -> [])."""
    if not tag_ids:
        return []
    body = api_get("/similarjobs", {"id": job_id, "tags": ",".join(str(t) for t in tag_ids), "cat": category_id,
                                    "exp": min_experience, "size": size, "pageName": "JD"},
                   label=f"similar jobs of {job_id}")
    return body.get("data") if isinstance(body.get("data"), list) else []


# ---- vocabularies --------------------------------------------------------------------------------

def tags():
    """[{categoryId, tags: [{id, name, count}]}] — every skill tag with its job count."""
    return api_get("/tags", label="skill tags", expect=list)


def tag_info(slug):
    body = api_get("/taginfo", {"slug": slug}, label=f"tag {slug!r}")
    rows = body.get("data") if isinstance(body.get("data"), list) else []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def suggest(query):
    body = api_get("/search/keyword", {"query": query}, label=f"suggestions {query!r}", expect=list)
    return [s for s in body if isinstance(s, str)]


def industries():
    """{industries: [{label, value}], trendingIndustries: [{id, label, value: 't-<id>'}]}."""
    body = api_get("/data/industry", label="industries")
    data = body.get("data")
    if not isinstance(data, dict):
        raise IimjobsUpstreamError("unexpected industry payload")
    return data


def extract_params(query):
    """The site's AI search: a sentence -> {extracted_query, extracted_parameters:
    {jobTitles, skills, companyNames, industries, locations, experience, jobPosted}}."""
    body = _request("POST", refdata.API_URL + "/extract-param", f"query reading {query!r}", dict, JOB_HEADERS,
                    json_body={"query": query})
    if not body.get("success"):
        raise IimjobsUpstreamError(f"the site could not read the query {query!r}")
    return body


# ---- companies -------------------------------------------------------------------------------------

def company_list(page):
    body = api_get("/company-list", {"page": page}, label=f"company list p{page}")
    if not isinstance(body.get("docs"), list):
        raise IimjobsUpstreamError(f"unexpected company list payload (page {page})")
    return body


def company_search(keyword):
    body = api_get("/company-list/search", {"page": 0, "keyword": keyword}, label=f"company search {keyword!r}")
    if not isinstance(body.get("docs"), list):
        raise IimjobsUpstreamError(f"unexpected company search payload for {keyword!r}")
    return body


def _record(path, params, label):
    body = api_get(path, params, label=label)
    data = body.get("data")
    return data if isinstance(data, dict) else {}


def company_record(slug):
    """A company page's record by its slug ({} when the slug has none)."""
    return _record("/company-id-slug", {"slug": slug}, f"company page {slug!r}")


def company_slug(company_id):
    """A company page's record by the company id ({} when it has no page)."""
    return _record("/company-slug", {"id": company_id}, f"company page of {company_id}")


def company_data(slug):
    """The AmbitionBox profile behind a company page; {} when there is none."""
    return _record("/company-data", {"slug": slug}, f"company {slug!r}")


def company_jobs(company_id, page=0):
    """One page (15) of a company's open jobs -> {jobs, hasMore, count, count1Year}."""
    body = api_get("/top-jobs", {"page": page, "cid": company_id}, label=f"jobs of company {company_id} p{page}")
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    return {"jobs": data.get("jobs") if isinstance(data.get("jobs"), list) else [],
            "hasMore": bool(data.get("hasMore")), "count": body.get("count"), "count1Year": body.get("count1Year")}


def company_slugs():
    body = api_get("/companies/slugs", label="company slugs")
    return body.get("data") if isinstance(body.get("data"), list) else []


# ---- recruiters -------------------------------------------------------------------------------------

def recruiter(recruiter_id):
    """The recruiter profile; IimjobsNotFound for an unknown id (the service
    answers a bare 500 'Internal Server Error' for one — not retried)."""
    body = _request("GET", _url(refdata.API_URL, "/data/recruiter", {"id": recruiter_id}),
                    f"recruiter {recruiter_id}", dict, JOB_HEADERS, missing_on_500=True)
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("id"):
        raise IimjobsNotFound(f"iimjobs has no recruiter with the id {recruiter_id}")
    return data


def recruiter_jobs(recruiter_id, page=0):
    return _feed("/recruiterfeed/", {"recruiterId": recruiter_id, "page": page},
                 f"jobs of recruiter {recruiter_id} p{page}")


# ---- courses (iimjobs Learning) ------------------------------------------------------------------------

def courses(category_id=0):
    """Every published course (category_id 0) or one category's -> the raw
    course records ([] when the category has none: the service answers
    {"error_msg": "No Course Found"} with HTTP 200)."""
    body = learning_get(f"/v2/courses/{int(category_id)}", label=f"courses of category {category_id}")
    rows = body.get("CourseList")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def course_detail(course_id):
    """(the full course record, its snapshot) — two calls, in parallel.
    IimjobsNotFound when the course does not exist."""
    def record():
        body = learning_get(f"/v2/course/0/user/{course_id}/detail", label=f"course {course_id}")
        rows = body.get("data") if isinstance(body.get("data"), list) else []
        return rows[0] if rows and isinstance(rows[0], dict) else None

    def snapshot():
        body = learning_get(f"/v2/course/{course_id}", label=f"course {course_id} snapshot")
        return body if body.get("courseID") else None

    (rs, rec), (ss, snap) = run_parallel([record, snapshot], 2)
    if rs == "error":
        raise rec
    if rec is None:
        raise IimjobsNotFound(f"iimjobs has no course with the id {course_id}")
    return rec, (snap if ss == "ok" else None)


# ---- memo / cache ------------------------------------------------------------------------------------------

_memo = OrderedDict()

_memo_lock = threading.Lock()

MEMO_TTL = 600

MEMO_MAX = 64

def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


def shared_raw(name, params, build, ttl):
    """An upstream payload shared by several routes: in-process memo, then
    the service's response cache (pods share it) when one is installed,
    then build(). Without a `cache` module (the standalone package) it is
    the in-process memo alone."""
    try:
        from cache import cached_call
    except ImportError:
        cached_call = None
    seconds = ttl.total_seconds() if hasattr(ttl, "total_seconds") else ttl
    key = ("iimjobs", name, json.dumps(params, sort_keys=True))
    if cached_call is None:
        return memoized(key, build, ttl=min(seconds, MEMO_TTL))
    return memoized(key, lambda: cached_call(f"iimjobs.raw.{name}", params, lambda **_: build(), ttl),
                    ttl=min(seconds, MEMO_TTL))


if __name__ == "__main__":
    # Smoke test: python iimjobs/fetch.py
    body = search({"query": "product manager", "page": 0, "size": 5, "loc": "3"})
    print("search:", body.get("totalJobs"), [j.get("title") for j in body["data"][:3]])
    job = job_detail(body["data"][0]["id"])
    print("job:", job.get("title"), job.get("min"), job.get("max"), len(job.get("introText") or ""))
    print("company jobs:", company_jobs(30).get("count"))
    print("recruiter:", recruiter(65).get("name"))
    print("courses:", len(courses()))
