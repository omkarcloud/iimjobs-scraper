"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (iimjobs/fixtures/*.gz, raw payloads captured 2026-10-19 from
gladiator.iimjobs.com and lng-api.iimjobs.com) — no network.

    python -m pytest iimjobs/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from iimjobs import companies, courses, fetch, jobs, lookups, parsers as P, recruiters, refdata, refs, schemas  # noqa: E402
from iimjobs import shared as S  # noqa: E402
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "1740408", "https://www.iimjobs.com/j/piramal-product-manager-1740408", "www.iimjobs.com/j/x-1740408/",
    "piramal-product-manager-1740408", "https://iimjobs.com/j/1740408?ref=x", "https://www.iimjobs.tech/j/y-1740408",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == 1740408


@pytest.mark.parametrize("value", ["", "abc", "https://www.iimjobs.com/k/sales-jobs", "https://example.com/j/x-1/",
                                   "https://www.hirist.tech/j/x-1740408"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


def test_resolve_jobs():
    assert refs.resolve_jobs("1740408, https://www.iimjobs.com/j/x-1740555, 1740408") == [1740408, 1740555]
    with pytest.raises(ValueError):
        refs.resolve_jobs(", ,")
    with pytest.raises(ValueError):
        refs.resolve_jobs(",".join(str(i) for i in range(1, refdata.MAX_BATCH + 2)))


@pytest.mark.parametrize("value,expected", [
    ("30", {"id": 30, "slug": None, "name": None}),
    ("https://www.iimjobs.com/kpmg-careers", {"id": None, "slug": "kpmg", "name": None}),
    ("iimjobs.com/piramal-pharma-careers/", {"id": None, "slug": "piramal-pharma", "name": None}),
    ("piramal-pharma", {"id": None, "slug": "piramal-pharma", "name": None}),
    ("kpmg-careers", {"id": None, "slug": "kpmg", "name": None}),
    ("KPMG", {"id": None, "slug": None, "name": "KPMG"}),
    ("ICICI Bank", {"id": None, "slug": None, "name": "ICICI Bank"}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "0", "https://www.iimjobs.com/k/sales-jobs", "https://example.com/x-careers", "a/b"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


@pytest.mark.parametrize("value", ["65", "https://www.iimjobs.com/r/65-sibal-vertexcorp-com", "65-sibal", "http://www.iimjobs.com/r/65-Sibal"])
def test_resolve_recruiter(value):
    assert refs.resolve_recruiter(value) == 65


@pytest.mark.parametrize("value", ["", "abc", "https://www.iimjobs.com/j/x-1740408", "https://example.com/r/1-x"])
def test_resolve_recruiter_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_recruiter(value)


def test_resolve_course():
    assert refs.resolve_course("2930") == 2930
    assert refs.resolve_course("https://www.iimjobs.com/course/IIM-Kashipur-%7C-Executive-Program-Financial-Analytics-%26-AI-2930") == 2930
    assert refs.resolve_course("https://www.iimjobs.com/course/ICFAI-Online%20%7C%20Online%20MBA-2859") == 2859
    for bad in ("abc", "https://www.iimjobs.com/j/x-2930", "https://example.com/course/x-1"):
        with pytest.raises(ValueError):
            refs.resolve_course(bad)


def test_resolve_locations():
    assert refs.resolve_locations("bengaluru, Remote, Mumbai, bombay, 4") == [3, 132, 2, 4]
    assert refs.resolve_locations("gurgaon") == [37]
    assert refs.resolve_locations("Delhi NCR") == [1, 36, 40, 41, 37, 38, 39]
    assert refs.resolve_locations("Anywhere in India/Multiple Locations")[0] == 88
    assert refs.resolve_locations("") is None
    with pytest.raises(ValueError):
        refs.resolve_locations("Atlantis")


def test_resolve_categories():
    assert refs.resolve_categories("banking-finance, Sales & Marketing, 15, hr, consulting-general-mgmt-jobs, genai") == [13, 14, 15, 17, 16, 25]
    assert refs.resolve_categories("supply chain, legal-jobs, BPO") == [19, 21, 22]
    with pytest.raises(ValueError):
        refs.resolve_categories("astrology")


def test_resolve_industries():
    assert refs.resolve_industries("FinTech, 2, t-3, pharma, edtech, b2b saas, IT, banking") == ["t-1", "2", "t-3", "28", "t-6", "14"]
    with pytest.raises(ValueError, match="several"):
        refs.resolve_industries("services")
    with pytest.raises(ValueError):
        refs.resolve_industries("zzqqxx")


# ---- schemas ---------------------------------------------------------------------------------

def test_search_schema():
    data, err = load_query(schemas.JobSearchSchema, {"query": "product manager", "location": "bangalore,remote",
                                                     "industry": "fintech", "posted_within": "5", "min_experience": "2",
                                                     "page": "2", "page_size": "50"})
    assert err is None
    assert data["location"] == [3, 132] and data["industry"] == ["t-1"] and data["posted_within"] == 5
    assert data["page"] == 2 and data["page_size"] == 50 and data["skill"] is None and data["include_details"] is False
    assert data["smart_search"] is False
    for bad in ({"posted_within": "0"}, {"page_size": "101"}, {"location": "Atlantis"}, {"bogus": "1"},
                {"page": "101", "page_size": "100"}, {"min_experience": "10", "max_experience": "5"}):
        _, err = load_query(schemas.JobSearchSchema, bad)
        assert err, bad
    _, err = load_query(schemas.JobSearchSchema, {"page": "100", "page_size": "100"})
    assert err is None


def test_other_schemas():
    data, err = load_query(schemas.JobSchema, {"job": "https://www.iimjobs.com/j/x-1740408"})
    assert err is None and data == {"job": 1740408}
    data, err = load_query(schemas.CompanySchema, {"company": "kpmg-careers", "include_jobs": "false"})
    assert err is None and data == {"company": {"id": None, "slug": "kpmg", "name": None}, "include_jobs": False}
    data, err = load_query(schemas.RecruiterJobsSchema, {"recruiter": "65"})
    assert err is None and data == {"recruiter": 65, "page": 1}
    data, err = load_query(schemas.SkillsSchema, {"category": "banking-finance", "limit": "5"})
    assert err is None and data == {"category": [13], "query": None, "limit": 5}
    data, err = load_query(schemas.CourseSearchSchema, {"category": "finance", "max_work_experience": "3"})
    assert err is None and data["category"] == [13] and data["max_work_experience"] == 3
    _, err = load_query(schemas.CompanySearchSchema, {"query": "icici", "page": "2"})
    assert err and "page" in err["errors"]
    _, err = load_query(schemas.CompanySearchSchema, {"page": str(refdata.COMPANY_LIST_MAX_PAGE + 1)})
    assert err
    _, err = load_query(schemas.AutocompleteSchema, {})
    assert err


# ---- shared ----------------------------------------------------------------------------------

def test_shared_helpers():
    assert S.utc_datetime_ms(1792151137995) == "2026-10-16T11:45:37Z" and S.site_date_ms(1792151137995) == "2026-10-16"
    assert S.site_date_ms(1792089000000) == "2026-10-16"                    # IST midnight stays on its own day
    assert S.utc_datetime_ms(0) is None and S.utc_datetime("2024-11-19T12:28:36.000Z") == "2024-11-19T12:28:36Z"
    assert S.link("http://www.iimjobs.com/r/65-Sibal") == "https://www.iimjobs.com/r/65-Sibal"
    assert S.link("https://www.iimjobs.tech/j/x-1740602") == "https://www.iimjobs.com/j/x-1740602"
    assert S.job_link(1740408, "Piramal - Product Manager ") == "https://www.iimjobs.com/j/piramal-product-manager-1740408"
    assert S.company_link("kpmg") == "https://www.iimjobs.com/kpmg-careers"
    assert S.skill_link("IT Jobs in BFSI") == "https://www.iimjobs.com/k/it-jobs-in-bfsi-jobs"
    assert S.course_link(2930, "IIM Kashipur | Executive Program Financial Analytics & AI") == \
        "https://www.iimjobs.com/course/IIM-Kashipur-%7C-Executive-Program-Financial-Analytics-%26-AI-2930"
    assert S.job_title("NIIT - Sales Specialist (5-8 yrs)") == "NIIT - Sales Specialist"
    assert S.job_title("Manager (Finance) ") == "Manager (Finance)"
    assert S.company_id_from_logo("https://rec-assets.iimjobs.com/CompanyLogos/centralised-175.webp") == 175
    assert S.company_id_from_logo(".../CompanyLogos/centralised-0.webp") is None and S.logo(".../CompanyLogos/centralised-0.webp") is None
    assert S.apply_link("https://ad.doubleclick.net/ddm/clk/1;2;k;gdpr=${GDPR}?https://careers.x.com/job/1?utm_source=n&utm_term=2&id=5") \
        == "https://careers.x.com/job/1?id=5"
    assert S.apply_link("https://jobs.lever.co/meesho/abc/apply?lever-source=iimjobs") == "https://jobs.lever.co/meesho/abc/apply?lever-source=iimjobs"
    assert S.apply_link("") is None
    assert S.person("Shveta Verma<br>\nInclusion and Diversity Leader") == ("Shveta Verma", "Inclusion and Diversity Leader")
    assert S.rich_text("<p></p>") == (None, None) and S.rich_text("<p><b>Role</b></p>") == ("<p><b>Role</b></p>", "Role")
    assert S.course_fee("INR 1,40,000 + GST") == {"text": "INR 1,40,000 + GST", "min": 140000, "max": 140000,
                                                  "currency": "INR", "is_gst_extra": True}
    assert S.course_fee("1.5 to 2.8 lakhs")["min"] == 150000 and S.course_fee("1.5 to 2.8 lakhs")["max"] == 280000
    assert S.course_fee("INR 21,00,000 (Upto 30% scholarships on merit)")["min"] == 2100000
    assert S.course_fee("INR 2.50,000")["min"] == 250000 and S.course_fee("USD 999")["currency"] == "USD"
    assert S.course_fee(None)["text"] is None
    assert S.duration_months("6 Months") == 6 and S.duration_months("2 Years") == 24 and S.duration_months("35 Weeks") == 8.1
    assert S.ids_from_csv("2,13,14") == [2, 13, 14] and S.ids_from_csv([2, 2, None]) == [2]


# ---- parsers: jobs --------------------------------------------------------------------------------

def test_job_card_rich():
    card = P.job_card(fx("search_pm")["data"][0])
    assert card["id"] == 1740408 and card["title"] == "Piramal - Product Manager" and card["designation"] == "Product Manager"
    assert card["link"] == "https://www.iimjobs.com/j/piramal-product-manager-1740408"
    assert card["category"] == {"id": 15, "slug": "it-systems-jobs", "name": "IT & Systems",
                                "link": "https://www.iimjobs.com/c/it-systems-jobs"}
    assert card["experience"] == {"min_years": 1, "max_years": 6} and card["salary"]["is_disclosed"] is False
    assert card["skills"][0] == {"id": 80, "name": "IT Product Management", "is_mandatory": True,
                                 "link": "https://www.iimjobs.com/k/it-product-management-jobs"}
    assert card["skills"][-1]["is_mandatory"] is False
    assert card["locations"] == [{"id": 3, "name": "Bangalore", "is_remote": False}] and card["is_remote"] is False
    assert card["industries"][0] == {"id": 2, "name": "Banking / Financial Services / Broking"}
    assert card["trending_industries"] == [{"id": 1, "name": "FinTech"}]
    assert card["stats"] == {"applications": 353, "views": 562, "recruiter_actions": 0}
    assert card["posted_at"] == "2026-10-16T11:45:37Z" and card["posted_date"] == "2026-10-16"
    company = card["company"]
    assert company["id"] == 175 and company["name"] == "Piramal Pharma Limited" and company["domain"] == "piramal.com"
    assert company["sectors"] == ["Pharmaceuticals/Medical Companies"] and company["slug"] is None
    assert set(company["ambitionbox"]) == set(P.AMBITIONBOX_SUMMARY_KEYS) and company["ambitionbox"]["founded_year"] == 2020
    assert card["recruiter"] == {"id": 203068, "name": "Md. Ghufran Ansari", "designation": "Manager - Human Resources",
                                 "photo": "https://edgar.iimjobs.com/media/recruiterpics/2023/03/29/2023-03-29-18-03-94-203068.jpg",
                                 "link": "https://www.iimjobs.com/r/203068-md-ghufran-ansari"}
    dumped = json.dumps(card)
    for junk in ("tagIdString", "refCode", "marker", "createdByAlias", "minRatingAb", "seo"):
        assert junk not in dumped


def test_job_card_slim_and_feeds():
    card = P.job_card(fx("keyword_sales")["data"][0])
    assert card["id"] == 1740492 and card["category"] is None and card["recruiter"] is None
    assert card["stats"] == {"applications": None, "views": None, "recruiter_actions": None} and card["industries"] == []
    assert card["company"]["id"] == 22959 and card["company"]["name"] == "Hireginie"      # id read from the logo
    one = P.job_card(fx("category_finance")["data"][0], category_id=13)
    assert one["category"]["name"] == "Banking & Finance"
    women = P.job_card(fx("women")["data"]["jobs"][0])
    assert women["title"] == "Shopalyst - Brand Solutions Specialist" and women["description_text"]
    assert women["diversity"]["prefers_women"] is True
    similar = P.job_card(fx("similar")["data"][0])
    assert similar["id"] == 1736761 and similar["salary"]["is_disclosed"] is False


def test_feed_results():
    out = P.feed_result(fx("search_pm"), 1, 20)
    assert len(out["jobs"]) == 20 and out["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 203,
                                                            "total_count": 4051}
    assert out["jobs_last_year"] == 29767
    board = P.feed_result(fx("category_board"), 1, 20)
    assert board["pagination"]["total_count"] == 25847 and board["pagination"]["total_pages"] == 500   # the 10,000 window
    women = P.offset_feed_result(fx("women")["data"], 2, 20)
    assert women["pagination"] == {"page": 2, "items_per_page": 20, "total_pages": 21, "total_count": 417}
    recruiter = P.feed_result(fx("recruiter_jobs"), 1, 20)
    assert recruiter["pagination"]["total_count"] == 57 and recruiter["pagination"]["total_pages"] == 3


def test_job_details():
    job = P.job_details(fx("detail")["data"], company_page={"slug": "piramal", "link": None})
    assert job["id"] == 1740408 and job["description_html"].startswith("<p><b>Role Overview") and job["description_text"]
    assert job["stats"] == {"applications": 353, "views": None, "recruiter_actions": 0}          # views masked logged out
    assert job["recruiter"]["name"] is None and job["recruiter"]["designation"] == "Manager - Human Resources"
    assert job["company"]["slug"] == "piramal" and job["company"]["ambitionbox"]["benefits"]["count"] == 9
    assert job["company"]["ambitionbox"]["top_job_profiles"] and job["is_active"] is True and job["has_expired"] is False
    assert job["company"]["ambitionbox"]["about"].startswith("Piramal Finance Limited") and "<" not in job["company"]["ambitionbox"]["about"]
    assert list(job)[:7] == ["id", "title", "designation", "link", "category", "experience", "graduation_batch"]
    expired = P.job_details(fx("detail_expired")["data"])
    assert expired["is_active"] is False and expired["has_expired"] is True and expired["is_removed"] is True
    inactive = P.job_details(fx("detail_inactive")["data"])
    assert inactive["is_active"] is False and inactive["has_expired"] is False
    salary = P.job_details(fx("detail_salary")["data"])
    assert salary["salary"] == {"min": 3000000, "max": 4000000, "min_lakhs": 30.0, "max_lakhs": 40.0, "currency": "INR",
                                "period": "year", "is_disclosed": True}
    apply = P.job_details(fx("detail_apply")["data"])
    assert apply["apply_link"] == "https://careers.amgen.com/job/-/-/87/101559434192?source=rd_naukri&ss=paid"
    other = P.job_details(fx("detail_other_locations")["data"])
    assert other["other_locations"] == ["Northeast", "Tripura", "Meghalaya"] and [l["name"] for l in other["locations"]] == ["Assam", "Others"]
    confidential = P.job_details(fx("detail_confidential")["data"])
    assert confidential["is_confidential"] is True and confidential["company"] is None and confidential["recruiter"] is None
    showcase = P.job_details(fx("detail_showcase")["data"])["showcase"]
    assert showcase["name"] == "Wipro Limited" and showcase["link"].startswith("https://showcase.iimjobs.com/") and showcase["images"]
    program = P.job_details(fx("detail_diversity")["data"])["diversity_program"]
    assert program["name"] == "PricewaterhouseCoopers Professional Services LLP" and "WoMentoring" in program["programs"]
    assert program["testimonials"][0]["name"] == "Shveta Verma" and program["testimonials"][0]["designation"]
    assert not program["testimonials"][0]["quote"].startswith('"')
    assert P.job_details({}) is None


def test_merge_card_details():
    card = P.job_card(fx("search_pm")["data"][0])
    details = P.job_details(fx("detail")["data"])
    merged = P.merge_card_details(card, details)
    assert merged["description_html"] and merged["stats"]["views"] == 562 and merged["recruiter"]["name"] == "Md. Ghufran Ansari"
    assert details["stats"]["views"] is None                    # the detail itself is not mutated
    assert P.merge_card_details(card, None) is card


# ---- parsers: companies / recruiters / lookups / courses --------------------------------------------

def test_company_cards():
    cards = [P.company_card(d) for d in fx("company_list")["docs"]]
    cognizant = cards[1]
    assert cognizant["id"] == 6290 and cognizant["name"] == "Cognizant" and cognizant["slug"] == "cognizant"
    assert cognizant["link"] == "https://www.iimjobs.com/cognizant-careers" and cognizant["jobs_count"] == 14
    assert cognizant["showcase"]["name"] == "Cognizant Technology Solutions" and cognizant["sectors"]
    assert "rating" not in cognizant and S.labels(["FinTech Companies", "Fintech Companies", "Start-ups"]) == ["FinTech Companies", "Start-ups"]
    assert all(c["description"] is None or "View All Jobs" not in c["description"] for c in cards)
    listing = P.company_list_result(fx("company_list"), 3, 50)
    assert listing["pagination"] == {"page": 3, "items_per_page": 50, "total_pages": 4, "total_count": None}
    last = P.company_list_result(fx("company_list"), refdata.COMPANY_LIST_MAX_PAGE, 50)
    assert last["pagination"]["total_pages"] == refdata.COMPANY_LIST_MAX_PAGE
    icici = P.company_card(fx("company_search")["docs"][0])
    assert icici["name"] == "ICICI Securities" and icici["id"] == 2945 and icici["ambitionbox"]["rating"] == 3.9   # the index lower-cases names
    record = P.company_card(fx("company_record_kpmg")["data"])
    assert record["id"] == 30 and record["name"] == "kpmg" and record["link"] is None
    jobs = [P.job_card(j) for j in fx("company_jobs_kpmg")["data"]["jobs"]]
    from_jobs = P.company_from_jobs(jobs)
    assert from_jobs["id"] == 30 and from_jobs["name"] == "KPMG Assurance and Consulting Services" and from_jobs["ambitionbox"]["rating"]
    merged = P.merge_company_cards(record, from_jobs)
    assert merged["name"] == "KPMG Assurance and Consulting Services" and merged["slug"] == "kpmg" and merged["ambitionbox"]


def test_company_profile_and_jobs():
    raw_jobs = fx("company_jobs_kpmg")["data"]["jobs"]
    profile = P.company_profile(30, "kpmg", fx("company_record_kpmg")["data"], fx("company_data_empty")["data"], raw_jobs,
                                jobs_count=55)
    assert profile["id"] == 30 and profile["name"] == "KPMG Assurance and Consulting Services" and profile["link"] is None
    assert profile["ambitionbox"]["name"] == "KPMG India" and profile["domains"] == ["kpmg.com"] and profile["jobs_count"] == 55
    jindal = P.company_profile(15842, "jindal-stainless", fx("company_record_jindal")["data"],
                               fx("company_data_jindal")["data"], [])
    assert jindal["link"] == "https://www.iimjobs.com/jindal-stainless-careers" and jindal["ambitionbox"]["rating"] == 4.1
    assert jindal["name"] == "Jindal Stainless" and jindal["ambitionbox"]["benefits"]["count"] == 6
    out = P.company_jobs_result(fx("company_jobs_kpmg"), 1)
    assert len(out["jobs"]) == 15 and out["pagination"] == {"page": 1, "items_per_page": 15, "total_pages": 4, "total_count": 55}
    assert out["jobs"][0]["description_html"] and out["jobs"][0]["company"]["id"] == 30


def test_recruiter_profile():
    rec = P.recruiter_profile(fx("recruiter")["data"])
    assert rec["id"] == 65 and rec["name"] == "Sibal" and rec["organisation"] == "Vertex Corporate Services"
    assert rec["link"] == "https://www.iimjobs.com/r/65-Sibal" and rec["website"] == "https://vertexcorp.com/"
    assert rec["hiring_for"][0] == {"id": 124, "name": "CA", "jobs_count": 601, "link": "https://www.iimjobs.com/k/ca-jobs"}
    assert "uuid" not in rec and rec["last_active_date"]


def test_lookup_parsers():
    table = P.skill_table(fx("tags"))
    assert len(table) == 9 and table[0]["category"]["id"] == 13
    assert table[0]["skills"][0] == {"id": 124, "name": "CA", "jobs_count": 67148, "link": "https://www.iimjobs.com/k/ca-jobs"}
    info = P.tag_info(fx("taginfo")["data"][0])
    assert info["id"] == 155 and info["slug"] == "sales" and info["jobs_count_all_time"] == 325072
    industries = P.industry_table(fx("industries")["data"])
    assert len(industries["industries"]) == 66 and industries["trending_industries"][0] == {"id": 1, "name": "FinTech", "filter_value": "t-1"}
    assert {r["id"]: r["name"] for r in industries["industries"]} == refdata.INDUSTRIES      # the static copy is current
    read = P.interpreted_query(fx("extract_param"))
    assert read == {"query": "Product Manager", "job_titles": ["Product", "Manager"], "skills": [], "companies": [],
                    "location_ids": [3], "industry_values": ["t-1"], "min_experience": 4, "max_experience": 6,
                    "posted_within_days": None}


def test_courses_parsers():
    rows = [P.course(r) for r in fx("courses")["CourseList"]]
    assert len(rows) == 32 and all(r["id"] and r["title"] and r["link"] for r in rows)
    first = rows[0]
    assert first["id"] == 2859 and first["institute"] == "ICFAI" and first["fee"]["min"] == 200000
    assert first["duration_months"] == 24 and first["categories"][0] == {"id": 13, "name": "Banking & Finance"}
    assert first["curriculum_html"] is None                       # '<p></p>' upstream
    assert all(c["id"] > 0 for r in rows for c in r["categories"])      # the '-1' placeholder row is dropped
    full = P.course(fx("course_detail")["data"][0], fx("course_snapshot"))
    assert full["id"] == 2930 and full["accreditation"] == "IIM Kashipur" and full["fee"]["is_gst_extra"] is True
    assert len(full["skills"]) == 11 and full["updated_at"] == "2026-09-30T04:31:49Z" and full["eligibility_text"]
    assert full["link"] == "https://www.iimjobs.com/course/IIM-Kashipur-%7C-Executive-Program-Financial-Analytics-%26-AI-2930"
    snapshot_only = P.course({}, fx("course_snapshot"))
    assert snapshot_only["id"] == 2930 and [c["id"] for c in snapshot_only["categories"]] == [13, 16, 25]
    assert P.course({}) is None


# ---- transport classification ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, status, body, headers=None):
        self.status_code, self.headers = status, headers or {}
        self.text = body if isinstance(body, str) else json.dumps(body)


def test_classify():
    with pytest.raises(fetch.IimjobsNotFound):
        fetch._classify(_Resp(404, fx("detail_missing")), "job 999999999")
    with pytest.raises(fetch.IimjobsNotFound):
        fetch._classify(_Resp(500, {"error": {"statusCode": 500, "message": "Internal Server Error"}}), "recruiter 1",
                        missing_on_500=True)
    with pytest.raises(fetch.IimjobsUpstreamError) as err:
        fetch._classify(_Resp(500, {"error": {"statusCode": 500, "message": "Internal Server Error"}}), "search")
    assert not isinstance(err.value, fetch.IimjobsNotFound)
    with pytest.raises(fetch.IimjobsBlocked):
        fetch._classify(_Resp(429, "slow down"), "search")
    with pytest.raises(fetch.IimjobsBlocked):
        fetch._classify(_Resp(403, "<title>Just a moment...</title>", {"cf-mitigated": "challenge"}), "search")
    with pytest.raises(fetch.IimjobsBadRequest):
        fetch._classify(_Resp(200, {"error": {"statusCode": 401, "name": "UNAUTHORISED_ACCESS", "message": "login"}}), "insights")
    with pytest.raises(fetch.IimjobsUpstreamError):
        fetch._classify(_Resp(200, "<html>oops</html>"), "search")
    assert fetch._classify(_Resp(200, fx("industries")), "industries")["data"]["industries"]


def test_courses_empty_category(monkeypatch):
    monkeypatch.setattr(fetch, "learning_get", lambda path, params=None, label=None, expect=dict: fx("courses_empty"))
    assert fetch.courses(13) == []


# ---- endpoint functions over fixtures ----------------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    calls = []

    def feed(kind, name):
        def serve(params, label=None):
            calls.append((kind, dict(params)))
            return fx(name)
        return serve

    def job_detail(job_id):
        calls.append(("detail", job_id))
        if job_id == 999999999:
            raise fetch.IimjobsNotFound("no")
        return fx("detail")["data"] if job_id == 1740408 else fx("detail_salary")["data"]

    monkeypatch.setattr(fetch, "search", lambda params, label=None: calls.append(("search", dict(params))) or (
        fx("search_kpmg") if params.get("query") == "kpmg" else fx("search_pm")))
    monkeypatch.setattr(fetch, "keyword_feed", feed("keyword", "keyword_sales"))
    monkeypatch.setattr(fetch, "category_feed", feed("category", "category_finance"))
    monkeypatch.setattr(fetch, "women_feed", lambda params, label=None: calls.append(("women", dict(params))) or fx("women")["data"])
    monkeypatch.setattr(fetch, "job_detail", job_detail)
    monkeypatch.setattr(fetch, "similar_jobs", lambda *a, **k: calls.append(("similar", a, k)) or fx("similar")["data"])
    monkeypatch.setattr(fetch, "extract_params", lambda q: fx("extract_param"))
    monkeypatch.setattr(fetch, "tags", lambda: fx("tags"))
    monkeypatch.setattr(fetch, "tag_info", lambda slug: None)
    monkeypatch.setattr(fetch, "suggest", lambda q: fx("suggest"))
    monkeypatch.setattr(fetch, "industries", lambda: fx("industries")["data"])
    monkeypatch.setattr(fetch, "company_list", lambda page: fx("company_list"))
    monkeypatch.setattr(fetch, "company_search", lambda keyword: fx("company_search") if "icici" in keyword.lower()
                        else {"numFound": 0, "docs": []})
    monkeypatch.setattr(fetch, "company_record", lambda slug: fx("company_record_kpmg")["data"] if slug == "kpmg"
                        else fx("company_record_jindal")["data"] if slug == "jindal-stainless" else {})
    monkeypatch.setattr(fetch, "company_slug", lambda cid: fx("company_slug_30")["data"] if cid == 30
                        else fx("company_slug_175")["data"] if cid == 175 else {})
    monkeypatch.setattr(fetch, "company_data", lambda slug: fx("company_data_jindal")["data"] if slug == "jindal-stainless" else {})
    monkeypatch.setattr(fetch, "company_jobs", lambda cid, page=0: {**fx("company_jobs_kpmg")["data"], "count": 55, "count1Year": 0}
                        if cid == 30 else {"jobs": [], "hasMore": False, "count": 0, "count1Year": 0})
    monkeypatch.setattr(fetch, "recruiter", lambda rid: fx("recruiter")["data"])
    monkeypatch.setattr(fetch, "recruiter_jobs", lambda rid, page=0: fx("recruiter_jobs"))
    monkeypatch.setattr(fetch, "courses", lambda category_id=0: fx("courses")["CourseList"])
    monkeypatch.setattr(fetch, "course_detail", lambda cid: (fx("course_detail")["data"][0], fx("course_snapshot")))
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())
    fetch._memo.clear()
    return calls


def test_jobs_search_dispatch(offline):
    out = jobs.search(query="product manager", location=[3, 132], industry=["t-1"], posted_within=7, category=[15],
                      page=2, page_size=20)
    assert offline[-1] == ("search", {"query": "product manager", "page": 1, "size": 20, "loc": "3,132", "minexp": None,
                                      "maxexp": None, "posting": 7, "industry": "t-1", "categoryId": "15"})
    assert out["pagination"]["page"] == 2 and out["filters"]["locations"] == [{"id": 3, "name": "Bangalore"}, {"id": 132, "name": "Remote"}]
    assert out["filters"]["industries"] == [{"id": 1, "name": "FinTech", "is_trending": True}]
    out = jobs.search(skill=["sales", 244], min_experience=2, page_size=50)
    assert offline[-1][0] == "keyword" and offline[-1][1]["keywordId"] == "155,244" and "categoryId" not in offline[-1][1]
    assert out["filters"]["skills"][0]["name"] == "Sales" and out["filters"]["skills"][1]["name"] == "Marketing"
    out = jobs.search(page_size=20)
    assert offline[-1][0] == "category" and offline[-1][1]["categoryId"] == "13,14,15,16,17,19,21,22,25"
    out = jobs.search(category=[13], page_size=20)
    assert offline[-1][1]["categoryId"] == "13" and out["jobs"][0]["category"]["id"] == 13
    for bad in (dict(query="sales", skill=["sales"]), dict(skill=["sales"], category=[13]), dict(skill=["no-such-zzz"]),
                dict(smart_search=True), dict(page=101, page_size=100)):
        with pytest.raises(ValueError):
            jobs.search(**bad)


def test_jobs_smart_search_and_details(offline):
    out = jobs.search(query="product manager jobs in bangalore 5 years fintech", smart_search=True)
    assert offline[-1][1]["query"] == "Product Manager" and offline[-1][1]["loc"] == "3" and offline[-1][1]["industry"] == "t-1"
    assert offline[-1][1]["minexp"] == 4 and out["filters"]["interpreted_query"]["location_ids"] == [3]
    out = jobs.search(query="product manager jobs in bangalore", smart_search=True, location=[2])
    assert offline[-1][1]["loc"] == "2"                                       # an explicit filter wins
    out = jobs.search(query="product manager", page_size=20, include_details=True)
    assert out["jobs"][0]["description_html"] and out["jobs"][0]["stats"]["views"] == 562
    assert out["jobs"][0]["company"]["slug"] == "piramal"


def test_jobs_women_details_batch_similar(offline):
    out = jobs.for_women(location=[2], category=[14], page=2, page_size=20)
    assert offline[-1] == ("women", {"femaleFilter": 1, "start": 20, "end": 40, "minExp": None, "maxExp": None,
                                     "joblocationIds": "2", "categoryIds": "14"})
    assert out["pagination"]["total_count"] == 417 and out["filters"]["locations"] == [{"id": 2, "name": "Mumbai"}]
    job = jobs.details(1740408)
    assert job["id"] == 1740408 and job["company"]["slug"] == "piramal" and job["company"]["link"] is None
    out = jobs.batch([1740408, 1740345, 999999999])
    assert out["count"] == 2 and out["errors"] == {"999999999": "not found"}
    with pytest.raises(fetch.IimjobsNotFound):
        jobs.details(999999999)
    out = jobs.similar(1740408, limit=5)
    assert out["job"]["id"] == 1740408 and out["count"] == 5 and out["jobs"][0]["id"] != 1740408


def test_companies(offline):
    out = companies.search(query="icici")
    names = [c["name"] for c in out["companies"]]
    assert "ICICI Securities" in names and out["pagination"]["total_count"] == len(names)
    out = companies.search(query="kpmg")
    assert out["companies"][0]["id"] == 30 and out["companies"][0]["name"] == "KPMG Assurance and Consulting Services"
    assert out["companies"][0]["slug"] == "kpmg"
    out = companies.search(page=2)
    assert out["pagination"]["page"] == 2 and len(out["companies"]) == 50
    out = companies.details({"id": None, "slug": "kpmg", "name": None})
    assert out["id"] == 30 and out["name"] == "KPMG Assurance and Consulting Services" and len(out["jobs"]) == 15
    assert out["jobs_count"] == 55 and out["link"] is None
    out = companies.details({"id": 30, "slug": None, "name": None}, include_jobs=False)
    assert out["slug"] == "kpmg" and out["jobs"] is None
    out = companies.details({"id": None, "slug": None, "name": "KPMG"})
    assert out["id"] == 30
    out = companies.details({"id": None, "slug": "jindal-stainless", "name": None})
    assert out["link"] == "https://www.iimjobs.com/jindal-stainless-careers" and out["jobs"] == [] and out["jobs_count"] == 0
    with pytest.raises(fetch.IimjobsNotFound):
        companies.details({"id": None, "slug": None, "name": "zzqqxx"})
    with pytest.raises(fetch.IimjobsNotFound):
        companies.details({"id": None, "slug": "zzqqxx-nope", "name": None})
    out = companies.open_jobs({"id": 30, "slug": None, "name": None}, page=1)
    assert out["company"]["id"] == 30 and out["company"]["slug"] == "kpmg" and out["pagination"]["total_count"] == 55


def test_recruiters_courses_lookups(offline):
    rec = recruiters.details(65)
    assert rec["name"] == "Sibal"
    out = recruiters.open_jobs(65)
    assert out["recruiter"]["id"] == 65 and out["pagination"]["total_count"] == 57
    out = courses.search(query="iim", category=[13], delivery_method="online", max_work_experience=5)
    assert out["count"] >= 3 and all("iim" in (c["title"] + c["institute"]).lower() for c in out["courses"])
    assert all((c["work_experience"]["min_years"] or 0) <= 5 for c in out["courses"])
    assert courses.search()["count"] == 32
    assert courses.details(2930)["accreditation"] == "IIM Kashipur"
    out = lookups.skills(category=[13], limit=3)
    assert out["count"] == 3 and out["categories"][0]["skills"][0]["name"] == "CA"
    out = lookups.skills(query="credit")
    assert all("credit" in s["name"].lower() for b in out["categories"] for s in b["skills"])
    assert lookups.categories()["count"] == 9
    locs = lookups.locations()
    metros = [g for g in locs["groups"] if g["name"] == "Metros"][0]
    assert locs["count"] == 163 and len(metros["members"]) == 15
    assert lookups.industries()["count"] == 71
    out = lookups.autocomplete("cred")
    assert out["suggestions"][0]["name"] == "Credit Analysis" and out["suggestions"][0]["skill"]["id"] == 367
