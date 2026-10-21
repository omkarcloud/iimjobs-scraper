"""/iimjobs/courses/* — iimjobs Learning: the executive programmes, online
MBAs and certificate courses (IIMs, IITs, ISB, online universities) the
site lists for working professionals — fee, duration, delivery mode,
work-experience band, eligibility, curriculum — from its course service
(lng-api.iimjobs.com)."""
import re

from iimjobs import cache_config as ttl
from iimjobs import fetch
from iimjobs import parsers as P


def _all_courses():
    """Every published course, parsed (one upstream call; cached)."""
    return fetch.shared_raw("courses", {}, lambda: [c for c in (P.course(r) for r in fetch.courses(0)) if c],
                            ttl.COURSES_CACHE)


def _words(value):
    return [w for w in re.split(r"[^a-z0-9]+", (value or "").lower()) if w]


def search(query=None, category=None, delivery_method=None, max_work_experience=None):
    """Every course iimjobs lists (a few dozen at a time), newest first,
    optionally narrowed: `query` (words in the title, institute or
    tagline), `category` (job categories the course is filed under),
    `delivery_method` (Online / Blended / Classroom, a substring match) and
    `max_work_experience` (courses open to candidates with that many years)."""
    rows = _all_courses()
    words = _words(query)
    out = []
    for row in rows:
        haystack = " ".join(_words(" ".join(filter(None, [row["title"], row["institute"], row["tagline"]]))))
        if words and not all(w in haystack for w in words):
            continue
        if category and not {c["id"] for c in row["categories"]} & set(category):
            continue
        if delivery_method and delivery_method.lower() not in (row["delivery_method"] or "").lower():
            continue
        if max_work_experience is not None and (row["work_experience"]["min_years"] or 0) > max_work_experience:
            continue
        out.append(row)
    out.sort(key=lambda r: -(r["id"] or 0))
    from iimjobs import lookups
    return {"courses": out, "count": len(out),
            "filters": {"query": query, "categories": lookups.category_refs(category),
                        "delivery_method": delivery_method, "max_work_experience": max_work_experience}}


def details(course):
    """One course in full: the list record plus its skills, last update, and
    the snapshot's accreditation and registration dates."""
    record, snapshot = fetch.course_detail(course)
    out = P.course(record, snapshot)
    if out is None:
        raise fetch.IimjobsNotFound(f"iimjobs has no course with the id {course}")
    return out
