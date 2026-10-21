"""Live endpoint smoke tests: one call per /iimjobs/* route against a
running service, with example values proven to return data (2026-10-19).
The listing tooling (derive_facts.py) reads each route's FIRST call from
this file's AST as its working example, so the values stay literals.

Skipped unless IIMJOBS_BASE points at a running service:

    SCRAPERS_PORT=6097 ONLY_SCRAPER=iimjobs python run.py
    IIMJOBS_BASE=http://127.0.0.1:6097 python -m pytest iimjobs/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("IIMJOBS_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set IIMJOBS_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/iimjobs/jobs/search", query="product manager", location="Bangalore", posted_within=30)
    assert body["count"] > 50 and body["per_page"] == 20 and len(body["jobs"]) == 20 and body["next"]
    job = body["jobs"][0]
    assert job["id"] and job["title"] and job["link"].startswith("https://www.iimjobs.com/j/")
    assert job["skills"][0]["name"] and job["experience"]["max_years"] and job["posted_at"].endswith("Z")
    assert job["company"]["name"] and job["company"]["id"] and job["recruiter"]["id"] and job["stats"]["views"] is not None
    assert body["filters"]["locations"] == [{"id": 3, "name": "Bangalore"}] and body["filters"]["posted_within_days"] == 30
    page2 = call("/iimjobs/jobs/search", query="product manager", location="Bangalore", posted_within=30, page=2)
    assert page2["current_page"] == 2 and page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/iimjobs/jobs/search", skill="sales, marketing", industry="Banking / Financial Services / Broking",
                min_experience=5, max_experience=10, page_size=5, include_details="true")
    assert body["count"] > 50 and len(body["jobs"]) == 5 and body["jobs"][0]["description_text"]
    assert body["filters"]["skills"][0]["name"] == "Sales" and body["filters"]["industries"][0]["id"] == 2
    body = call("/iimjobs/jobs/search", category="banking-finance", posted_within=7, page_size=50)
    assert len(body["jobs"]) == 50 and all(j["category"]["id"] == 13 for j in body["jobs"])
    body = call("/iimjobs/jobs/search", page_size=5)
    assert body["count"] > 10000 and body["total_pages"] == 2000 and body["filters"]["query"] is None
    body = call("/iimjobs/jobs/search", query="product manager jobs in bangalore fintech 5 years", smart_search="true")
    assert body["filters"]["query"] == "Product Manager" and body["filters"]["locations"][0]["id"] == 3
    assert body["filters"]["industries"][0]["name"] == "FinTech" and body["filters"]["interpreted_query"]
    assert status("/iimjobs/jobs/search", query="sales", skill="sales") == 400
    assert status("/iimjobs/jobs/search", skill="sales", category="banking-finance") == 400
    assert status("/iimjobs/jobs/search", skill="zzqqxx-not-a-skill") == 400
    assert status("/iimjobs/jobs/search", location="Atlantis") == 400
    assert status("/iimjobs/jobs/search", industry="zzqqxx") == 400
    assert status("/iimjobs/jobs/search", page=101, page_size=100) == 400


def test_jobs_for_women():
    body = call("/iimjobs/jobs/for-women", location="Mumbai")
    assert body["count"] > 10 and len(body["jobs"]) == 20 and body["jobs"][0]["diversity"]["prefers_women"] is True
    assert body["jobs"][0]["description_text"] and "yrs)" not in body["jobs"][0]["title"]
    page2 = call("/iimjobs/jobs/for-women", location="Mumbai", page=2)
    assert page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}


def test_job_details():
    listing = call("/iimjobs/jobs/search", query="product manager", location="Bangalore", page_size=3)
    job = listing["jobs"][0]
    body = call("/iimjobs/jobs/details", job=job["link"])
    assert body["id"] == job["id"] and body["description_html"] and body["description_text"]
    assert body["is_active"] is True and body["stats"]["applications"] is not None and body["recruiter"]["id"]
    assert body["company"]["id"] and body["category"]["slug"] and body["salary"]["currency"] == "INR"
    removed = call("/iimjobs/jobs/details", job=1600000)
    assert removed["is_active"] is False and removed["has_expired"] is True
    assert status("/iimjobs/jobs/details", job=999999999) == 404
    assert status("/iimjobs/jobs/details", job="abc") == 400


def test_job_batch_and_similar():
    listing = call("/iimjobs/jobs/search", query="finance manager", location="Mumbai", page_size=3)
    ids = [j["id"] for j in listing["jobs"][:3]]
    body = call("/iimjobs/jobs/batch", jobs=",".join(str(i) for i in ids + [999999999]))
    assert body["count"] == 3 and body["errors"] == {"999999999": "not found"}
    body = call("/iimjobs/jobs/similar", job=ids[0], limit=5)
    assert body["job"]["id"] == ids[0] and body["count"] == 5 and body["jobs"][0]["link"]


def test_company_search():
    body = call("/iimjobs/companies/search", query="icici")
    assert body["count"] >= 2 and any(c["name"] == "ICICI Bank" and c["id"] == 97 for c in body["companies"])
    assert any(c["slug"] == "icici-securities" and c["link"] for c in body["companies"])
    body = call("/iimjobs/companies/search", page=2)
    assert body["current_page"] == 2 and len(body["companies"]) == 50 and body["next"] and body["companies"][0]["slug"]
    assert status("/iimjobs/companies/search", query="icici", page=2) == 400


def test_company_details_and_jobs():
    body = call("/iimjobs/companies/details", company="KPMG")
    assert body["id"] == 30 and body["slug"] == "kpmg" and body["name"].startswith("KPMG")
    assert body["jobs_count"] >= 15 and len(body["jobs"]) == 15 and body["ambitionbox"]["rating"] and body["domains"]
    body = call("/iimjobs/companies/details", company="https://www.iimjobs.com/mobikwik-careers", include_jobs="false")
    assert body["slug"] == "mobikwik" and body["link"] == "https://www.iimjobs.com/mobikwik-careers" and body["jobs"] is None
    assert body["ambitionbox"]["benefits"] and body["sectors"]
    assert status("/iimjobs/companies/details", company="zzqqxx nonexistent corp") == 404
    body = call("/iimjobs/companies/jobs", company=30, page=2)
    assert body["count"] >= 16 and body["per_page"] == 15 and body["company"]["id"] == 30 and body["jobs"]
    assert body["jobs"][0]["description_text"] and body["jobs"][0]["company"]["id"] == 30


def test_recruiters():
    body = call("/iimjobs/recruiters/details", recruiter="https://www.iimjobs.com/r/65-sibal-vertexcorp-com")
    assert body["id"] == 65 and body["organisation"] == "Vertex Corporate Services" and body["hiring_for"][0]["jobs_count"]
    assert body["link"] == "https://www.iimjobs.com/r/65-Sibal" and body["last_active_date"]
    body = call("/iimjobs/recruiters/jobs", recruiter=65)
    assert body["count"] >= 1 and body["recruiter"]["id"] == 65 and body["jobs"][0]["recruiter"]["id"] == 65
    assert status("/iimjobs/recruiters/details", recruiter=999999999) == 404


def test_courses():
    body = call("/iimjobs/courses/search", query="iim")
    assert body["count"] >= 3 and all("iim" in (c["title"] + c["institute"]).lower() for c in body["courses"])
    course = body["courses"][0]
    assert course["fee"]["text"] and course["duration"] and course["link"] and course["description_text"]
    body = call("/iimjobs/courses/details", course=2930)
    assert body["id"] == 2930 and body["institute"] == "IIM Kashipur" and body["fee"]["min"] == 140000
    assert body["skills"] and body["categories"] and body["eligibility_text"]
    assert status("/iimjobs/courses/details", course=99999) == 404


def test_lookups():
    body = call("/iimjobs/skills", category="banking-finance", limit=5)
    assert body["count"] == 5 and body["categories"][0]["skills"][0]["name"] == "CA" and body["categories"][0]["skills"][0]["jobs_count"]
    body = call("/iimjobs/skills", query="credit")
    assert body["count"] > 3 and all("credit" in s["name"].lower() for c in body["categories"] for s in c["skills"])
    body = call("/iimjobs/categories")
    assert body["count"] == 9 and body["categories"][0]["slug"] == "banking-finance-jobs"
    body = call("/iimjobs/locations")
    assert body["count"] == 163 and body["groups"] and any(l["name"] == "Bangalore" and l["id"] == 3 for l in body["locations"])
    body = call("/iimjobs/industries")
    assert body["count"] > 60 and body["trending_industries"][0] == {"id": 1, "name": "FinTech", "filter_value": "t-1"}
    body = call("/iimjobs/autocomplete", query="cred")
    assert body["suggestions"][0]["name"].startswith("Credit") and body["suggestions"][0]["skill"]["id"]
    assert status("/iimjobs/autocomplete") == 400
