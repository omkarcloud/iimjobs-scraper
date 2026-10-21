"""Cache TTL per /iimjobs/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so an omitted param and its
default share a row).

iimjobs' feeds move hourly (new ads, refreshes, premium re-ranking); one ad
changes rarely once posted (its application count daily); company and
recruiter profiles move daily at most; the skill table's job counts move
daily; company page records and the course catalogue are stable for days."""
from datetime import timedelta

# --- raw upstream payloads shared by several routes (fetch.shared_raw) ----------
TAGS_RAW_CACHE = timedelta(days=1)            # /tags (skill names -> ids, job counts)
COMPANY_PAGE_CACHE = timedelta(days=7)        # /company-slug, /company-id-slug, a name's best match
INTERPRET_CACHE = timedelta(days=7)           # /extract-param (a sentence -> filters)
COURSES_CACHE = timedelta(hours=12)           # lng-api /v2/courses/0

# --- jobs -----------------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=1)
JOB_CACHE = timedelta(hours=6)
SIMILAR_CACHE = timedelta(hours=6)

# --- companies ----------------------------------------------------------------------------
COMPANY_CACHE = timedelta(days=1)             # also the AmbitionBox profile (/company-data)
COMPANY_SEARCH_CACHE = timedelta(hours=12)
COMPANY_JOBS_CACHE = timedelta(hours=3)

# --- recruiters ----------------------------------------------------------------------------
RECRUITER_CACHE = timedelta(days=1)
RECRUITER_JOBS_CACHE = timedelta(hours=3)

# --- courses / lookups ------------------------------------------------------------------------
COURSE_CACHE = timedelta(days=1)
SKILLS_CACHE = timedelta(days=1)
LOOKUPS_CACHE = timedelta(days=7)
AUTOCOMPLETE_CACHE = timedelta(days=7)
