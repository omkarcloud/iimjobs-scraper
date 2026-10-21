"""The 17 IIMJobs endpoints. Every path is served with and without the
`/iimjobs` prefix, so code generated against the hosted API on RapidAPI
(paths like /jobs/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(iimjobs/schemas.py), and paginated endpoints answer in the same shape:
count / per_page / current_page / total_pages / next / previous, then the
data."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, NotFound
from iimjobs import companies, courses, jobs, lookups, recruiters, schemas


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Gurgaon/Gurugram" or "₹" would arrive garbled)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "", False)}
    query["page"] = page
    host = request.urlparts.netloc or "localhost:8000"
    return f"{request.urlparts.scheme or 'http'}://{host}{path}?{urlencode(query, doseq=True)}"


def paginate(result, path, raw):
    """Lift the scraper's `pagination` block into the flat API shape."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = _as_int(pagination.get("page")) or _as_int(raw.get("page")) or 1
    total_pages = max(_as_int(pagination.get("total_pages")), 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, raw, page + 1 if page < total_pages else None),
        "previous": _page_link(path, raw, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, impl, paginated=False):
    """Validate -> run -> shared error mapping: bad params -> 400, missing
    entity -> 404, transport / blocks -> 500."""
    raw = query_dict()
    data, error = load_query(schema, raw)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:                # bad params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # upstream rejected the request
        return json_response({"error": f"iimjobs rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"iimjobs {path.strip('/')} failed: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


ENDPOINTS = [
    # jobs
    ("/jobs/details", schemas.JobSchema, jobs.details, False),
    ("/jobs/search", schemas.JobSearchSchema, jobs.search, True),
    ("/jobs/batch", schemas.JobBatchSchema, jobs.batch, False),
    ("/jobs/similar", schemas.SimilarJobsSchema, jobs.similar, False),
    ("/jobs/for-women", schemas.WomenJobsSchema, jobs.for_women, True),
    # companies
    ("/companies/details", schemas.CompanySchema, companies.details, False),
    ("/companies/jobs", schemas.CompanyJobsSchema, companies.open_jobs, True),
    ("/companies/search", schemas.CompanySearchSchema, companies.search, True),
    # recruiters
    ("/recruiters/details", schemas.RecruiterSchema, recruiters.details, False),
    ("/recruiters/jobs", schemas.RecruiterJobsSchema, recruiters.open_jobs, True),
    # courses (iimjobs Learning)
    ("/courses/search", schemas.CourseSearchSchema, courses.search, False),
    ("/courses/details", schemas.CourseSchema, courses.details, False),
    # lookups
    ("/autocomplete", schemas.AutocompleteSchema, lookups.autocomplete, False),
    ("/skills", schemas.SkillsSchema, lookups.skills, False),
    ("/categories", schemas.EmptySchema, lookups.categories, False),
    ("/locations", schemas.EmptySchema, lookups.locations, False),
    ("/industries", schemas.EmptySchema, lookups.industries, False),
]


def mount(path, schema, impl, paginated):
    """Serve one endpoint at /path and /iimjobs/path."""
    def handler():
        return call(path, schema, impl, paginated)
    handler.__name__ = "iimjobs_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/iimjobs" + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
