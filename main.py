"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from iimjobs import refs
from iimjobs.companies import details as company_details
from iimjobs.jobs import details as job_details
from iimjobs.jobs import search as search_jobs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a job id or any iimjobs.com job link
    save("job_1739531.json", job_details(refs.resolve_job("1739531")))

    # 20 jobs per page; location takes names or ids (refs resolves them like the API does)
    save("search_product_manager_bangalore.json",
         search_jobs(query="product manager", location=refs.resolve_locations("Bangalore")))

    # a company id, a /<slug>-careers link or a name
    save("company_amazon.json", company_details(refs.resolve_company("Amazon")))
