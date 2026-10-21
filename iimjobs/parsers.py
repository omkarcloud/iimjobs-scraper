"""Raw iimjobs payloads -> the API's response shapes. Pure functions over
the job service's and iimjobs Learning's JSON (fetch.py); every parser
tolerates a partial record. The AmbitionBox company profile, location
entries, diversity flags and graduation batch read the same records as
hirist/parsers.py (hirist.tech runs the same job service).

Feeds differ in richness: /search, /female-jobs, /top-jobs, /recruiterfeed/
and /similarjobs cards carry the recruiter, the application / view counts,
the industries and the full AmbitionBox block (and /female-jobs, /top-jobs
the description); the /keyword/ and /category/ cards are slim (no
recruiter, counts, category or industries — those keys are null; the
company id is read back from the logo's file name). Cards carry a summary
of the company's AmbitionBox profile; job details and company pages the
full one.

Dropped on purpose (and why):
  jobs      `refCode` / `refJobId` / `marker` (promotion tracking codes),
            `score` / `_class` / `index` (search-engine internals),
            `tagIdString` (the `tags` list as a string), `createdTime` /
            `createdTimeNoMillis` (the posting date rounded to IST midnight
            — `createdTimeMs` is the exact stamp), `location` (a copy of
            `locations`), `createdByAlias` (the locations joined with '/'),
            `createdBy` (the recruiter's id again), `minRatingAb` (a sitewide
            threshold), `star` / `applyStatus` / `saved` / `applied` /
            `pendingApply` / `isEvaluationGated` / `isAppActiveWithinLastYear`
            / `showCompanyLogoFlag` / `showRecruiterProfile` / `brandJobFlag`
            / `salShow` / `refreshStatus` (per-visitor or presentation state),
            `status` / `state` / `companyStatus` (folded into is_active, or of
            unknown meaning), `functionalArea` (an id the site never names),
            `jobCount` (the recruiter's job total on the recruiter feed, 1 on
            details — not a per-job value), `jobCompanyId` / `jobCompanyLogo`
            (a recruitment agency's hidden client), `categoryIds` /
            `latitude` / `longitude` / `address` / `companyDomain` /
            `lableId` / `jobStatusInfo` / `jobJdContent` (always null),
            `careerCompanyName` (the AmbitionBox-matched page; the company's
            own page is resolved instead), `companyData.companyId` (an
            internal id no endpoint accepts), `companyNameNotAnalyzed` /
            `logoPath` / `companyLogoFilePath` (copies), `cluster` /
            `subCluster` (the ids of `sectors` / `sub_sectors`),
            `recruiter.recruiterCompanyId` / `centralizedCompanyId` (the
            company id — `company.id`), `recruiter.firstRecrTime` (unknown
            meaning), `ambitionBoxInfo.seo` (page titles for the site's own
            templates), `title` / `aggregateRatingOneDecimal` (repeats),
            showcase `quoteLineNo` / `custId` / `templatePath` /
            `templateVersion` / `showcaseVersion` (the page builder's
            internals), diversity `quoteLine` / `custId` / `jsonFilePath`,
            perk `logo` (an icon-font code point).
  companies `pageTitle` / `metaKeywords` / `metaDescription` / `source` /
            `refCode` (SEO templates), `id` (the page record's own row id),
            `companyIds` / `companyId` (an internal id no endpoint accepts),
            `custId`, `status`, `type`, `locationIds` (empty), `brandJobFlag`,
            `ambitionBoxName` / `ambitionBoxId` / `ambitionBoxData` (copies of
            `ambitionBoxInfo`), `redirectionLink` (rebuilt as `link`).
  recruiter `uuid` (the id and email base64-encoded), `recruiterTags[].
            tagNameLower`, `logoLink` (empty).
  courses   `pushtitle` (a marketing banner line), `brochure` (the file is
            released only after an enquiry), `hits` (an unlabelled counter
            next to `views`), `mobilecat` / `homecat` / `mobilefeatured` /
            `homefeatured` / `afterJobDisplayFlag` / `categoryStatus` /
            `state` / `blacklisted` / `ctaText` / `courseImageCDN` /
            `surveyEnabled` / `alreadyEnquired` / `showOnSimilarCoursesList` /
            `strictExpFilterEnabled` / `locationFilterEnabled` /
            `similarCourseLocationFilterEnabled` / `disableEnquiryOnDownload`
            / `show_brochure` / `institute_show` / `showEnquiry` /
            `EnquiryText` / `course_mailer_detail` (presentation switches),
            `createdBy` (an admin id).
"""
import re
from math import ceil

from iimjobs import refdata
from iimjobs import shared as S
from iimjobs.shared import as_dict, as_list, g

PLACEHOLDER_COMPANY_NAMES = {"verified company"}       # what a confidential ad shows instead of the employer


# ---- taxonomy entries ------------------------------------------------------------------------------------

def category_ref(category_id):
    cid = S.to_int(category_id)
    if not cid:
        return None
    slug, name = refdata.CATEGORIES.get(cid, (None, None))
    return {"id": cid, "slug": slug, "name": name, "link": S.category_link(slug)}


def skill_ref(raw):
    raw = as_dict(raw)
    name = S.text(raw.get("name") or raw.get("tagName"))
    if not name and raw.get("id") is None:
        return None
    return {"id": S.to_int(raw.get("id") or raw.get("tagId")), "name": name,
            "is_mandatory": S.flag(raw.get("isMandatory")) if "isMandatory" in raw else None,
            "link": S.skill_link(name)}


def industry_refs(raw):
    """`industryArray` [2, 13] (or the `industry` string '2,13') -> [{id, name}]."""
    ids = S.ids_from_csv(raw.get("industryArray") if isinstance(raw.get("industryArray"), list) else raw.get("industry"))
    return [{"id": i, "name": refdata.INDUSTRIES.get(i)} for i in ids]


def trending_industry_refs(raw):
    """`preferedIndustry` [{text: 'FinTech', value: 1}] -> [{id: 1, name: 'FinTech'}]."""
    out = []
    for row in as_list(raw.get("preferedIndustry")):
        row = as_dict(row)
        tid = S.to_int(row.get("value"))
        name = S.text(row.get("text")) or refdata.TRENDING_INDUSTRIES.get(tid)
        if tid or name:
            out.append({"id": tid, "name": name})
    return out


def location_ref(raw):
    raw = as_dict(raw)
    name = S.text(raw.get("name"))
    if not name:
        return None
    loc_id = S.to_int(raw.get("id"))
    return {"id": loc_id, "name": name, "is_remote": name.lower() in refdata.REMOTE_NAMES}


def _locations(raw):
    out = []
    for row in as_list(raw.get("locations") or raw.get("location")):
        entry = location_ref(row)
        if entry and entry["name"] not in [e["name"] for e in out]:
            out.append(entry)
    return out


# ---- AmbitionBox ------------------------------------------------------------------------------------------

def _benefit(raw):
    raw = as_dict(raw)
    return {"name": S.text(raw.get("name")), "icon": S.link(raw.get("iconUrl")),
            "reported_by": S.count(raw.get("count")), "respondents": S.count(raw.get("totalCount"))}

def _job_profile(raw):
    raw = as_dict(raw)
    return {"name": S.text(raw.get("name")), "rating": S.rating(raw.get("rating")),
            "reviews_count": S.count(raw.get("count")), "link": S.link(raw.get("url"))}

def ambitionbox_profile(raw):
    """The AmbitionBox block the site attaches to companies (job cards,
    company pages): identity, about, size, rating, benefits, job profiles."""
    raw = as_dict(raw)
    if not raw or not (raw.get("ambitionBoxCompanyId") or raw.get("companyName")):
        return None
    benefits = raw.get("benefits")
    if isinstance(benefits, dict):      # the company page nests the list under its own counts
        benefit_rows, benefits_link = benefits.get("benefits"), benefits.get("benefitsUrl")
        total_benefits, reported = benefits.get("totalBenefits"), benefits.get("usersReportedBenefits")
    else:
        benefit_rows, benefits_link = benefits, raw.get("benefitsUrl")
        total_benefits, reported = raw.get("totalBenefits"), raw.get("usersReportedBenefits")
    profiles = raw.get("topJobProfilesEntities")
    if not isinstance(profiles, list):
        profiles = g(raw, "topJobProfiles", "entities")
    offices = []
    for row in as_list(raw.get("officeLocations")):
        city = S.text(row.get("cityName") if isinstance(row, dict) else row)
        if city and city not in offices:
            offices.append(city)
    return {
        "id": S.to_int(raw.get("ambitionBoxCompanyId")),
        "name": S.text(raw.get("companyName")),
        "logo": S.link(raw.get("companyLogo")),
        "about": S.html_to_text(raw.get("aboutCompany")),
        "founded_year": S.year(raw.get("foundedYear")),
        "company_type": S.text(raw.get("companyType")),
        "primary_industry": S.text(raw.get("primaryIndustry")),
        "nature_of_business": S.text_list(raw.get("natureOfBusiness")),
        "tags": S.text_list(raw.get("otherTags")),
        "headquarters": S.text(raw.get("hq")),
        "office_locations": offices,
        "employees": S.text(raw.get("totalEmployees")),
        "employees_india": S.text(raw.get("totalEmployeesIndia")),
        "rating": S.rating(raw.get("aggregateRating")),
        "reviews_count": S.count(raw.get("reviewsCount")),
        "reviews_link": S.link(raw.get("url")),
        "benefits": {
            "count": S.count(total_benefits),
            "reported_by": S.count(reported),
            "link": S.link(benefits_link),
            "items": [_benefit(b) for b in as_list(benefit_rows) if isinstance(b, dict)],
        },
        "top_job_profiles": [_job_profile(p) for p in as_list(profiles) if isinstance(p, dict)],
        "top_job_profiles_link": S.link(raw.get("topJobProfilesUrl")),
    }


AMBITIONBOX_SUMMARY_KEYS = ("id", "name", "logo", "rating", "reviews_count", "reviews_link", "company_type",
                            "primary_industry", "employees_india", "founded_year", "headquarters")


def ambitionbox_summary(raw):
    """The AmbitionBox profile cut to what a job card needs (the benefits and
    the per-role ratings are identical on every job of a company and come
    with /jobs/details and /companies/details)."""
    full = ambitionbox_profile(raw)
    if not full:
        return None
    return {k: full[k] for k in AMBITIONBOX_SUMMARY_KEYS}


# ---- showcase / diversity programme pages ------------------------------------------------------------------

def showcase(raw):
    """The employer's paid showcase page (showcase.iimjobs.com)."""
    raw = as_dict(raw)
    if not raw or not (raw.get("showcaseUrl") or raw.get("showcaseName")):
        return None
    return {
        "id": S.to_int(raw.get("showcaseCompanyId") or raw.get("centralisedCompanyID")),
        "name": S.text(raw.get("showcaseName")),
        "link": S.link(raw.get("showcaseUrl")),
        "description": S.text(raw.get("description")),
        "perks": S.text_list([as_dict(p).get("title") for p in as_list(raw.get("perks"))]),
        "images": [S.link(i) for i in as_list(raw.get("showcaseImages")) if S.link(i)],
    }


def _testimonial(raw):
    raw = as_dict(raw)
    name, designation = S.person(raw.get("name"))
    quote = S.text(raw.get("about"))
    if not name and not quote:
        return None
    return {"name": name, "designation": designation, "photo": S.link(raw.get("image")),
            "quote": quote.strip("\"“”") if quote else None}


def diversity_program(raw):
    """The employer's diversity & inclusion page (diversity.iimjobs.com):
    programmes, photos and leaders' testimonials."""
    raw = as_dict(raw)
    if not raw or not (raw.get("diversityUrl") or raw.get("diversityName")):
        return None
    return {
        "id": S.to_int(raw.get("diversityId")),
        "name": S.text(raw.get("diversityName")),
        "link": S.link(raw.get("diversityUrl")),
        "logo": S.link(raw.get("companyLogo")),
        "banner": S.link(raw.get("bannerMobile")),
        "programs": S.text_list([as_dict(p).get("title") for p in as_list(raw.get("perksBenefit"))]),
        "images": [S.link(i) for i in as_list(raw.get("diversityImages")) if S.link(i)],
        "testimonials": [t for t in (_testimonial(r) for r in as_list(raw.get("testimonials"))) if t],
    }


# ---- companies and recruiters on job cards ------------------------------------------------------------------

def _company_name(value):
    name = S.text(value)
    return None if not name or name.lower() in PLACEHOLDER_COMPANY_NAMES else name


def job_company(job, full_ambitionbox=False, page=None):
    """The hiring company of a job. `id` is the company id every other
    /iimjobs/companies/* call takes (the recruiter's centralised company id;
    on slim cards read from the logo's file name). `page` is the company's
    page record (slug + whether it has a live page) when the caller looked
    it up — job details do, feeds do not (slug / link null)."""
    job = as_dict(job)
    raw = as_dict(job.get("companyData"))
    recruiter = as_dict(job.get("recruiter"))
    logo_src = raw.get("companyLogoFilePath") or raw.get("logo") or raw.get("logoPath") or recruiter.get("logoPath")
    company_id = S.to_int(recruiter.get("centralizedCompanyId")) or S.company_id_from_logo(logo_src)
    name = _company_name(raw.get("companyName"))
    domain = S.text(job.get("creatorDomainName"))
    if not (company_id or name or domain):
        return None
    profile = (ambitionbox_profile if full_ambitionbox else ambitionbox_summary)(raw.get("ambitionBoxInfo"))
    page = as_dict(page)
    return {
        "id": company_id,
        "name": name,
        "slug": page.get("slug"),
        "link": page.get("link"),
        "logo": S.logo(logo_src) or (profile or {}).get("logo"),
        "domain": domain,
        "sectors": S.labels(raw.get("clustersDetail")),
        "sub_sectors": S.labels(raw.get("subClustersDetail")),
        "ambitionbox": profile,
    }


def job_recruiter(raw):
    raw = as_dict(raw)
    rid = S.to_int(raw.get("recruiterId"))
    if not rid:
        return None
    name = S.text(raw.get("recruiterName"))       # '*****' (masked on /detail for anonymous callers) -> None
    return {
        "id": rid,
        "name": name,
        "designation": S.text(raw.get("designation")),
        "photo": S.link(raw.get("profilePicUrl")),
        "link": S.recruiter_link(rid, name),
    }


# ---- job cards --------------------------------------------------------------------------------------------

def diversity_flags(raw):
    return {
        "prefers_women": S.flag(raw.get("femaleCandidate")),
        "welcomes_women_returning_to_work": S.flag(raw.get("femaleBackWorkForce")),
        "is_open_to_differently_abled": S.flag(raw.get("differentlyAbled")),
        "is_open_to_ex_defence": S.flag(raw.get("exDefence")),
    }

def graduation_batch(raw):
    lo, hi = S.year(raw.get("minBatch")), S.year(raw.get("maxBatch"))
    if lo is None and hi is None:
        return None
    return {"min_year": lo, "max_year": hi}


def _job_link(raw, job_id, title):
    given = S.link(raw.get("jobDetailUrl"))
    if given and S.job_id_from_link(given) == job_id:
        return given
    return S.job_link(job_id, title)


def job_card(raw, category_id=None):
    """A feed card (search / skill / category / women / company / recruiter /
    similar feeds). `category_id` fills the category of slim cards when the
    feed was one category's."""
    raw = as_dict(raw)
    job_id = S.to_int(raw.get("id"))
    title = S.job_title(raw.get("title"))
    locations = _locations(raw)
    description_html, description_text = S.rich_text(raw.get("introText"))
    posted = raw.get("createdTimeMs") or raw.get("createdTime")
    recruiter = as_dict(raw.get("recruiter"))
    return {
        "id": job_id,
        "title": title,
        "designation": S.text(raw.get("jobdesignation")),
        "link": _job_link(raw, job_id, title),
        "category": category_ref(raw.get("categoryId") or category_id),
        "experience": {"min_years": S.to_int(raw.get("min")), "max_years": S.to_int(raw.get("max"))},
        "salary": S.salary(raw.get("minSal"), raw.get("maxSal"), raw.get("hideSal") if "hideSal" in raw else 1),
        "skills": [s for s in (skill_ref(t) for t in as_list(raw.get("tags"))) if s],
        "locations": locations,
        "other_locations": S.split_list(raw.get("otherLocation")),
        "is_remote": any(l["is_remote"] for l in locations) or bool(S.flag(raw.get("workFromHome"))),
        "is_work_from_home": S.flag(raw.get("workFromHome")),
        "industries": industry_refs(raw),
        "trending_industries": trending_industry_refs(raw),
        "description_html": description_html,
        "description_text": description_text,
        "apply_link": S.apply_link(raw.get("applyUrl")),
        "is_premium": S.flag(raw.get("premium")),
        "is_branded": S.flag(raw.get("brandedJd")),
        "is_confidential": S.flag(raw.get("confidential")),
        "has_assessment": bool(S.to_int(raw.get("assessmentFlags"))),
        "requires_video_resume": S.flag(raw.get("mediaResume")),
        "diversity": diversity_flags(raw),
        "stats": {
            "applications": S.count(raw.get("applyCount")),
            "views": S.count(raw.get("hits")),
            "recruiter_actions": S.count(recruiter.get("recruiterActions")),
        },
        "posted_at": S.utc_datetime_ms(posted),
        "posted_date": S.site_date_ms(posted),
        "company": job_company(raw),
        "recruiter": job_recruiter(recruiter),
        "showcase": showcase(raw.get("showcase")),
        "diversity_program": diversity_program(raw.get("diversity")),
    }


def results_window_pages(page_size):
    """The deepest page a listing serves (it answers the first 10,000 results)."""
    return ceil(refdata.MAX_RESULTS_WINDOW / page_size) if page_size else 0


def feed_result(raw, page, page_size, category_id=None):
    """A /search, /keyword/, /category/, /recruiterfeed/ page -> {jobs,
    jobs_last_year, pagination}. `page` is this API's 1-based page."""
    raw = as_dict(raw)
    total = S.count(raw.get("totalJobs"))
    size = S.to_int(raw.get("limit")) or page_size
    jobs = [job_card(c, category_id) for c in as_list(raw.get("data")) if isinstance(c, dict)]
    if total is not None:
        pages = min(ceil(total / size) if size else 0, results_window_pages(size))
    else:
        pages = page + 1 if raw.get("hasMore") else page
    return {
        "jobs": jobs,
        "jobs_last_year": S.count(raw.get("count1Year")),
        "pagination": {"page": page, "items_per_page": size, "total_pages": max(pages, page if jobs else 0),
                       "total_count": total},
    }


def offset_feed_result(raw, page, page_size):
    """A {jobs, count, hasMore} feed paged by offset (/female-jobs) -> {jobs, pagination}."""
    raw = as_dict(raw)
    total = S.count(raw.get("count"))
    jobs = [job_card(c) for c in as_list(raw.get("jobs")) if isinstance(c, dict)]
    pages = ceil(total / page_size) if total else (page if jobs else 0)
    return {"jobs": jobs,
            "pagination": {"page": page, "items_per_page": page_size, "total_pages": max(pages, page if jobs else 0),
                           "total_count": total}}


# ---- job details ------------------------------------------------------------------------------------------

def job_details(raw, company_page=None):
    """The /detail record: the card (with the full AmbitionBox profile) plus
    the counts the detail page shows, the activity state and the rare
    fields (graduation batch, video). `company_page` = the company's own
    page ({slug, link}) when the caller resolved it."""
    raw = as_dict(raw)
    if raw.get("id") is None:
        return None
    card = job_card(raw)
    card["company"] = job_company(raw, full_ambitionbox=True, page=company_page)
    expired = S.flag(raw.get("hasExpired"))
    removed = S.flag(raw.get("permanentlyRemoved"))
    active = S.flag(raw.get("active"))
    card["stats"] = {
        "applications": S.count(raw.get("applicationCount")) if raw.get("applicationCount") is not None
        else card["stats"]["applications"],
        "views": card["stats"]["views"],
        "recruiter_actions": S.count(raw.get("recruiterActionCount")) if raw.get("recruiterActionCount") is not None
        else card["stats"]["recruiter_actions"],
    }
    extra = {
        "experience": {"graduation_batch": graduation_batch(raw)},
        "apply_link": {"video_link": S.link(raw.get("videoUrl")),
                       "branded_description_link": S.link(raw.get("brandedS3"))},
        "requires_video_resume": {
            "is_active": (active if active is not None else True) and not expired and not removed,
            "has_expired": bool(expired),
            "is_removed": bool(removed),
            "is_posted_via_ats": S.flag(raw.get("ats")),
            "is_crawled": S.flag(raw.get("crawled")),
        },
    }
    out = {}
    for key, value in card.items():         # the detail-only fields sit next to their kin
        out[key] = value
        out.update(extra.get(key, {}))
    return out


def merge_card_details(card, details):
    """A feed card + its /detail record (include_details): the detail's
    richer fields win; the card's counts and recruiter name survive the
    detail page's masking; the card's category (a one-category feed's)
    fills a detail without one."""
    if not details:
        return card
    out = dict(details)
    out["stats"] = dict(details["stats"])
    for key in ("applications", "views", "recruiter_actions"):
        if out["stats"].get(key) is None and card["stats"].get(key) is not None:
            out["stats"][key] = card["stats"][key]
    if out.get("recruiter") and card.get("recruiter") and not out["recruiter"].get("name"):
        out["recruiter"] = {**out["recruiter"], "name": card["recruiter"]["name"], "link": card["recruiter"]["link"]}
    out["category"] = out.get("category") or card.get("category")
    return out


# ---- companies ----------------------------------------------------------------------------------------------

def _proper_name(*names):
    """The first name that is not all lower-case (the page records lower-case
    every name), else the first name at all."""
    names = [n for n in (S.text(x) for x in names) if n]
    for name in names:
        if name != name.lower():
            return name
    return names[0] if names else None


def _directory_showcase(raw, company_name):
    """A directory record's showcase block — kept only when it names the same
    company (the index mismatches some: Robosoft's record carries Haleon's)."""
    raw = as_dict(raw)
    if not raw or not (raw.get("companyId") or raw.get("showcaseLink")):
        return None
    name = S.text(raw.get("companyName")) or ""
    mine = (company_name or "").lower()
    if name and mine and not (name.lower() in mine or mine in name.lower()
                              or name.lower().split()[0] == mine.split()[0]):
        return None
    return {
        "id": S.to_int(raw.get("companyId")),
        "name": name or None,
        "link": S.link(raw.get("showcaseLink")),
        "description": S.text(raw.get("description")),
        "perks": S.text_list([as_dict(p).get("title") for p in as_list(raw.get("perks"))]),
        "images": [S.link(i) for i in as_list(raw.get("images")) if S.link(i)],
    }


_BOILERPLATE_DESCRIPTION = re.compile(r"^Explore opportunities at .*View All Jobs", re.I | re.S)


def _description(value):
    """A company page's description; the template every page without one
    carries ('Explore opportunities at <name>. Please click on View All
    Jobs …') -> None."""
    value = S.text(value)
    return None if not value or _BOILERPLATE_DESCRIPTION.match(value) else value


def company_card(raw):
    """A company directory record (/company-list, /company-list/search) or a
    page record (/company-id-slug, /company-slug)."""
    raw = as_dict(raw)
    slug = S.text(raw.get("slug"))
    profile = ambitionbox_summary(raw.get("ambitionBoxInfo") or raw.get("ambitionBoxData"))
    name = _proper_name(raw.get("companyName"), (profile or {}).get("name"), raw.get("companyNames"))
    return {
        "id": S.to_int(raw.get("centralisedCompanyId")) or None,
        "name": name,
        "slug": slug,
        "link": S.company_link(slug) if profile else None,
        "logo": (profile or {}).get("logo"),
        "domains": S.split_list(raw.get("companyDomains")),
        "description": _description(raw.get("description")),
        "jobs_count": S.count(raw.get("jobCount")),
        "locations": S.text_list([as_dict(l).get("name") for l in as_list(raw.get("location"))]),
        "sectors": S.labels(raw.get("clustersDetail")),
        "sub_sectors": S.labels(raw.get("subClustersDetail")),
        "showcase": _directory_showcase(raw.get("showcaseData"), name),
        "ambitionbox": profile,
        "page_created_at": S.utc_datetime(raw.get("createdAt")),
        "page_updated_at": S.utc_datetime(raw.get("updatedAt")),
    }


def company_from_jobs(jobs):
    """A company card built from its job cards (a company found through the
    job search): the most common employer name, logo, domain, sectors and
    the AmbitionBox summary, with the number of matching jobs seen."""
    jobs = [j for j in as_list(jobs) if isinstance(j, dict) and j.get("company")]
    if not jobs:
        return None
    names = {}
    for job in jobs:
        name = job["company"].get("name")
        if name:
            names[name] = names.get(name, 0) + 1
    head = jobs[0]["company"]
    first = lambda key: next((j["company"][key] for j in jobs if j["company"].get(key)), None)  # noqa: E731
    profile = first("ambitionbox")
    return {
        "id": head.get("id"),
        "name": max(names, key=names.get) if names else None,
        "slug": None,
        "link": None,
        "logo": first("logo"),
        "domains": S.text_list([j["company"].get("domain") for j in jobs]),
        "description": None,
        "jobs_count": None,
        "locations": S.text_list([l["name"] for j in jobs for l in j.get("locations") or []]),
        "sectors": first("sectors") or [],
        "sub_sectors": first("sub_sectors") or [],
        "showcase": next((j["showcase"] for j in jobs if j.get("showcase")), None),
        "ambitionbox": profile,
        "page_created_at": None,
        "page_updated_at": None,
    }


def merge_company_cards(base, extra):
    """Two cards of one company (a page record and its jobs, say): the base
    wins, the extra fills its gaps; the name is the first proper-cased one
    (page records lower-case names) — the jobs' employer name first, as on
    /companies/details."""
    out = dict(base)
    for key, value in as_dict(extra).items():
        if out.get(key) in (None, [], {}) and value not in (None, [], {}):
            out[key] = value
    out["name"] = _proper_name(as_dict(extra).get("name"), base.get("name"))
    return out


def company_list_result(raw, page, page_size, one_page=False):
    """The directory (hasMore paging, no total) or a name search (one page,
    numFound = the total)."""
    raw = as_dict(raw)
    companies = [company_card(d) for d in as_list(raw.get("docs")) if isinstance(d, dict)]
    if one_page:
        return {"companies": companies, "pagination": {"page": page, "items_per_page": page_size,
                                                       "total_pages": 1 if companies else 0,
                                                       "total_count": len(companies)}}
    pages = min(page + 1, refdata.COMPANY_LIST_MAX_PAGE) if raw.get("hasMore") else page
    return {"companies": companies,
            "pagination": {"page": page, "items_per_page": page_size, "total_pages": pages, "total_count": None}}


def company_profile(company_id, slug, record, ambitionbox_raw, jobs_raw, jobs_count=None):
    """A company page: the page record (ids, names, domains), the AmbitionBox
    profile (the page's own, else the one attached to its jobs) and what its
    open jobs say (employer name, logo, sectors, showcase, diversity
    programme). `jobs_raw` = raw /top-jobs cards (page 1)."""
    record = as_dict(record)
    cards = [job_card(j) for j in as_list(jobs_raw) if isinstance(j, dict)]
    from_jobs = company_from_jobs(cards) or {}
    raw_profile = ambitionbox_raw if as_dict(ambitionbox_raw) else next(
        (g(j, "companyData", "ambitionBoxInfo") for j in as_list(jobs_raw)
         if isinstance(j, dict) and as_dict(g(j, "companyData", "ambitionBoxInfo")).get("ambitionBoxCompanyId")), None)
    profile = ambitionbox_profile(raw_profile)
    has_page = bool(as_dict(ambitionbox_raw))          # the site serves /<slug>-careers only with a profile
    domains = S.split_list(record.get("companyDomains"))
    for domain in from_jobs.get("domains") or []:
        if domain not in domains:
            domains.append(domain)
    diversity = next((d for d in (diversity_program(g(j, "diversity")) for j in as_list(jobs_raw)) if d), None)
    return {
        "id": company_id or S.to_int(record.get("centralisedCompanyId")) or from_jobs.get("id"),
        "name": _proper_name(from_jobs.get("name"), (profile or {}).get("name"), record.get("companyNames")),
        "slug": slug,
        "link": S.company_link(slug) if slug and has_page else None,
        "logo": from_jobs.get("logo") or (profile or {}).get("logo"),
        "domains": domains,
        "description": _description(record.get("description")),
        "jobs_count": jobs_count,
        "sectors": from_jobs.get("sectors") or [],
        "sub_sectors": from_jobs.get("sub_sectors") or [],
        "showcase": from_jobs.get("showcase"),
        "diversity_program": diversity,
        "ambitionbox": profile,
        "page_created_at": S.utc_datetime(record.get("createdAt")),
        "page_updated_at": S.utc_datetime(record.get("updatedAt")),
    }


def company_jobs_result(raw, page):
    """A /top-jobs page (15 full records, `count` the total) -> {jobs, pagination}
    (its count1Year is always 0: not passed on)."""
    raw = as_dict(raw)
    if isinstance(raw.get("data"), dict):      # the backend's own envelope (fetch.company_jobs flattens it)
        raw = {**raw, **raw["data"]}
    total = S.count(raw.get("count"))
    size = refdata.COMPANY_JOBS_PAGE_SIZE
    jobs = [job_card(j) for j in as_list(raw.get("jobs")) if isinstance(j, dict)]
    pages = ceil(total / size) if total else (page if jobs else 0)
    return {"jobs": jobs,
            "pagination": {"page": page, "items_per_page": size, "total_pages": pages, "total_count": total}}


# ---- recruiters ----------------------------------------------------------------------------------------------

def recruiter_profile(raw):
    raw = as_dict(raw)
    rid = S.to_int(raw.get("id"))
    if not rid:
        return None
    name = S.text(raw.get("name"))
    skills = []
    for row in as_list(raw.get("recruiterTags")):
        row = as_dict(row)
        skill = S.text(row.get("tagName"))
        if skill:
            skills.append({"id": S.to_int(row.get("tagId")), "name": skill, "jobs_count": S.count(row.get("count")),
                           "link": S.skill_link(skill)})
    return {
        "id": rid,
        "name": name,
        "link": S.link(raw.get("profileUrl")) or S.recruiter_link(rid, name),
        "photo": S.link(raw.get("image")),
        "organisation": S.text(raw.get("organisation")),
        "designation": S.text(raw.get("designation")),
        "location": S.text(raw.get("location")),
        "about": S.text(raw.get("about")),
        "website": S.website(raw.get("website")),
        "social": {"linkedin": S.website(raw.get("linkedInUrl")), "facebook": S.website(raw.get("facebookUrl")),
                   "twitter": S.website(raw.get("twitterUrl"))},
        "last_login_date": S.iso_date(raw.get("lastLogin")),
        "last_active_date": S.iso_date(raw.get("lastActive")),
        "last_job_posted_date": S.iso_date(raw.get("lastJobPostedDate")),
        "hiring_for": skills,
    }


# ---- skills / industries ---------------------------------------------------------------------------------

def skill_table(raw):
    """/tags -> [{category, skills: [{id, name, jobs_count, link}]}]."""
    out = []
    for block in as_list(raw):
        block = as_dict(block)
        category = category_ref(block.get("categoryId"))
        skills = []
        for row in as_list(block.get("tags")):
            row = as_dict(row)
            name = S.text(row.get("name"))
            if name:
                skills.append({"id": S.to_int(row.get("id")), "name": name, "jobs_count": S.count(row.get("count")),
                               "link": S.skill_link(name)})
        if category or skills:
            out.append({"category": category, "skills": skills})
    return out


def tag_info(raw):
    raw = as_dict(raw)
    name = S.text(raw.get("tagName"))
    if not name:
        return None
    return {"id": S.to_int(raw.get("id")), "name": name, "slug": S.text(raw.get("tagSlug")),
            "link": S.skill_link(name), "description": S.text(raw.get("description")),
            "jobs_count_all_time": S.count(raw.get("tagCount"))}


def industry_table(raw):
    """/data/industry -> {industries: [{id, name, filter_value}], trending_industries: [...]}."""
    raw = as_dict(raw)
    regular = [{"id": S.to_int(r.get("value")), "name": S.text(r.get("label")), "filter_value": S.text(r.get("value"))}
               for r in (as_dict(x) for x in as_list(raw.get("industries"))) if S.text(r.get("label"))]
    trending = [{"id": S.to_int(r.get("id")), "name": S.text(r.get("label")), "filter_value": S.text(r.get("value"))}
                for r in (as_dict(x) for x in as_list(raw.get("trendingIndustries"))) if S.text(r.get("label"))]
    return {"industries": sorted(regular, key=lambda r: r["name"] or ""), "trending_industries": trending}


# ---- smart search ------------------------------------------------------------------------------------------

def interpreted_query(raw):
    """/extract-param -> what the site's AI search read from a sentence:
    {query, locations, industries, experience, skills, companies, posted_within_days}."""
    raw = as_dict(raw)
    params = as_dict(raw.get("extracted_parameters"))
    experience = as_dict(params.get("experience"))
    posted = as_dict(params.get("jobPosted"))
    return {
        "query": S.text(raw.get("extracted_query")),
        "job_titles": S.text_list(params.get("jobTitles")),
        "skills": S.text_list([as_dict(s).get("name") if isinstance(s, dict) else s for s in as_list(params.get("skills"))]),
        "companies": S.text_list([as_dict(s).get("name") if isinstance(s, dict) else s
                                  for s in as_list(params.get("companyNames"))]),
        "location_ids": [i for i in (S.to_int(as_dict(l).get("id")) for l in as_list(params.get("locations"))) if i],
        "industry_values": [str(as_dict(i).get("id")) for i in as_list(params.get("industries"))
                            if as_dict(i).get("id") not in (None, "")],
        "min_experience": S.to_int(experience.get("min")),
        "max_experience": S.to_int(experience.get("max")),
        "posted_within_days": S.to_int(posted.get("id")) or None,
    }


# ---- courses (iimjobs Learning) ----------------------------------------------------------------------------

def _course_categories(raw):
    out = []
    for row in as_list(raw.get("category")):
        row = as_dict(row)
        cid = S.to_int(row.get("id"))
        name = S.text(row.get("name")) or refdata.COURSE_CATEGORIES.get(cid)
        if cid and cid > 0 and cid not in [c["id"] for c in out]:      # '-1' is the service's placeholder row
            out.append({"id": cid, "name": name})
    if not out:      # the snapshot spells them '13,16,25'
        out = [{"id": i, "name": (refdata.CATEGORIES.get(i) or (None, refdata.COURSE_CATEGORIES.get(i)))[1]}
               for i in S.ids_from_csv(raw.get("course_cat_id"))]
    return out


def course(raw, snapshot=None):
    """A course record (/v2/courses/<cat> list rows or the /detail record),
    plus the snapshot (/v2/course/<id>: accreditation, registration dates)
    when given."""
    raw = as_dict(raw)
    snap = as_dict(snapshot)
    facts = as_dict(snap.get("course_snapshot"))
    course_id = S.to_int(raw.get("id") or snap.get("courseID"))
    if not course_id:
        return None
    title = S.text(raw.get("title") or snap.get("course_title"))
    description_html, description_text = S.rich_text(raw.get("introtext") or snap.get("course_detail"))
    eligibility_html, eligibility_text = S.rich_text(raw.get("desiredCandProfile") or snap.get("desired_cand_profile"))
    highlights_html, highlights_text = S.rich_text(raw.get("courseHighlight") or snap.get("course_highlight"))
    units_html, units_text = S.rich_text(raw.get("courseUnit") or snap.get("course_unit"))
    schedule_html, schedule_text = S.rich_text(raw.get("courseSchedule") or snap.get("course_schedule"))
    centers_html, centers_text = S.rich_text(raw.get("studyCenter") or snap.get("study_center"))
    duration = S.text(raw.get("duration") or facts.get("duration"))
    locations = S.text_list([as_dict(l).get("name") for l in as_list(raw.get("location"))]) or S.split_list(
        snap.get("location"))
    given_link = S.link(raw.get("url"))
    return {
        "id": course_id,
        "title": title,
        "link": given_link if given_link and given_link.endswith(f"-{course_id}") else S.course_link(course_id, title),
        "institute": S.text(raw.get("institute") or snap.get("institute")),
        "accreditation": S.text(snap.get("approved_certified") or raw.get("approved_certified")),
        "tagline": S.text(raw.get("oneLiner") or snap.get("one_liner")),
        "fee": S.course_fee(raw.get("fee") or facts.get("fee")),
        "duration": duration,
        "duration_months": S.duration_months(duration),
        "delivery_method": S.text(raw.get("deliveryMethod") or facts.get("delivery_method")),
        "work_experience": {"min_years": S.to_int(raw.get("minWorkExp")), "max_years": S.to_int(raw.get("maxWorkExp"))},
        "locations": locations,
        "categories": _course_categories(raw if raw.get("category") else snap),
        "skills": [{"id": S.to_int(as_dict(t).get("id")), "name": S.text(as_dict(t).get("name")),
                    "link": S.skill_link(as_dict(t).get("name"))}
                   for t in as_list(raw.get("tags")) if S.text(as_dict(t).get("name"))],
        "description_html": description_html,
        "description_text": description_text,
        "eligibility_html": eligibility_html,
        "eligibility_text": eligibility_text,
        "highlights_html": highlights_html,
        "highlights_text": highlights_text,
        "curriculum_html": units_html,
        "curriculum_text": units_text,
        "schedule_html": schedule_html,
        "schedule_text": schedule_text,
        "study_centers_html": centers_html,
        "study_centers_text": centers_text,
        "starts_on": S.iso_date(raw.get("courseStartOn") or facts.get("course_start_on")),
        "ends_on": S.iso_date(raw.get("courseCloseOn") or facts.get("course_close_on")),
        "registration": {"opens_on": S.iso_date(facts.get("reg_start_date")),
                         "closes_on": S.iso_date(facts.get("reg_end_date"))},
        "logo": S.link(raw.get("logo") or raw.get("path") or snap.get("logo")),
        "image": S.link(raw.get("courseImage")),
        "video_link": S.link(raw.get("videoLink") or snap.get("videourl")),
        "partner_link": S.link(raw.get("redirectUrl") or raw.get("lg_partner_url") or snap.get("redirectURL")),
        "is_premium": S.flag(raw.get("premiumFlag") if raw.get("premiumFlag") is not None else snap.get("premium_flag")),
        "views": S.count(raw.get("views")),
        "updated_at": S.utc_datetime(raw.get("modified")),
    }
