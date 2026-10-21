"""/iimjobs/recruiters/* — a recruiter's public profile (organisation,
designation, about, socials, activity dates, the skills they hire for)
and the jobs they have open."""
from iimjobs import fetch, refdata
from iimjobs import parsers as P


def details(recruiter):
    """The recruiter profile; 404 for an unknown id."""
    out = P.recruiter_profile(fetch.recruiter(recruiter))
    if out is None:
        raise fetch.IimjobsNotFound(f"iimjobs has no recruiter with the id {recruiter}")
    return out


def open_jobs(recruiter, page=1):
    """One page (20) of a recruiter's open jobs, newest first."""
    outcomes = fetch.run_parallel([lambda: details(recruiter), lambda: fetch.recruiter_jobs(recruiter, page - 1)], 2)
    for status, value in outcomes:
        if status == "error":
            raise value
    profile, raw = (v for _, v in outcomes)
    result = P.feed_result(raw, page, refdata.RECRUITER_JOBS_PAGE_SIZE)
    result["recruiter"] = {"id": profile["id"], "name": profile["name"], "link": profile["link"],
                           "organisation": profile["organisation"], "designation": profile["designation"]}
    return result
