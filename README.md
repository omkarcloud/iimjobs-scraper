# 💼 IIMJobs Scraper

IIMJobs Scraper is a **free and open-source** scraper that gets you **unlimited** detailed iimjobs management job data for free.

## ✨ What Can I Get?

- 💼 **25,000+ live management jobs** — full description, skills, experience band, applicant counts, recruiter & AmbitionBox company rating
- 🔍 **Search with every iimjobs filter** — keyword, skill, category, location, industry, experience & posting age, plus the site's AI search
- 🏢 **24,000+ company pages** — AmbitionBox rating, reviews, benefits, size, sectors & every open job
- 👔 **10,000+ recruiter profiles & IIM courses** — who's hiring, what they hire for, plus executive programmes with fees

## 🎥 Example: A Full iimjobs Job Ad

```json
{
  "id": 1739531,
  "title": "Amazon - Head - Sales & Marketing - D2C Solutions",
  "link": "https://www.iimjobs.com/j/amazon-head-sales-marketing-d2c-solutions-1739531",
  "category": { "id": 14, "slug": "sales-marketing-jobs", "name": "Sales & Marketing" },
  "experience": { "min_years": 10, "max_years": 20 },
  "skills": [
    { "id": 155, "name": "Sales", "is_mandatory": true, "link": "https://www.iimjobs.com/k/sales-jobs" },
    { "id": 2256, "name": "Go To Market", "is_mandatory": true, "link": "https://www.iimjobs.com/k/go-to-market-jobs" }
  ],
  "locations": [{ "id": 3, "name": "Bangalore", "is_remote": false }],
  "industries": [{ "id": 13, "name": "Internet / Online / eCommerce" }],
  "description_text": "Head of Sales & Marketing\n\nAbout the team:\n\nSmart Commerce helps emerging brands succeed in an increasingly complex, multi-channel commerce environment. ...",
  "stats": { "applications": 647, "recruiter_actions": 0 },
  "posted_date": "2026-10-13",
  "company": {
    "id": 126,
    "name": "Amazon",
    "domain": "amazon.com",
    "sectors": ["Internet / eCommerce Companies", "Fortune 500", "Global Capability Centers"],
    "ambitionbox": { "name": "Amazon Development Centre India", "rating": 3.8, "reviews_count": 7764, "employees_india": "10001-50000" }
  },
  "recruiter": { "id": 310650, "designation": "Recruiting Business Partner", "link": "https://www.iimjobs.com/r/310650" }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free IIMJobs Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/iimjobs-scraper
cd iimjobs-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=1739531"
```

```json
{
  "id": 1739531,
  "title": "Amazon - Head - Sales & Marketing - D2C Solutions",
  "designation": "Head - Sales & Marketing",
  "link": "https://www.iimjobs.com/j/amazon-head-sales-marketing-d2c-solutions-1739531",
  "experience": { "min_years": 10, "max_years": 20 },
  "locations": [{ "id": 3, "name": "Bangalore", "is_remote": false }],
  "is_active": true,
  "stats": { "applications": 649, "views": null, "recruiter_actions": 0 },
  "posted_at": "2026-10-13T08:42:59Z",
  "company": {
    "id": 126,
    "name": "Amazon",
    "slug": "amazon",
    "domain": "amazon.com",
    "ambitionbox": { "rating": 3.8, "reviews_count": 7764, "employees_india": "10001-50000" }
  },
  "recruiter": { "id": 310650, "designation": "Recruiting Business Partner" }
}
```

All 17 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

17 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | The full job ad: description, skills, applicants, recruiter, company rating |
| Search Jobs | `/jobs/search` | Up to 100 jobs per page with every filter and AI search |
| Batch Job Details | `/jobs/batch` | Full details for up to 10 jobs in one call |
| Similar Jobs | `/jobs/similar` | Up to 99 jobs iimjobs recommends for any job |
| Jobs for Women | `/jobs/for-women` | Roles whose recruiters prefer women candidates, with descriptions |
| Company Details | `/companies/details` | Rating, reviews, benefits, sectors, diversity programme and open jobs |
| Company Jobs | `/companies/jobs` | Every open job a company has, descriptions included |
| Search Companies | `/companies/search` | Find companies by name, or browse the whole directory |
| Recruiter Details | `/recruiters/details` | Organisation, activity dates, socials and the skills they hire for |
| Recruiter Jobs | `/recruiters/jobs` | A recruiter's open jobs, newest first |
| Search Courses | `/courses/search` | Executive courses and online MBAs with fee, duration and institute |
| Course Details | `/courses/details` | Fee, eligibility, curriculum, skills and accreditation |
| Autocomplete | `/autocomplete` | Skill and role suggestions with live job counts |
| Skills | `/skills` | 2,700+ skill tags with live job counts |
| Categories · Locations · Industries | `/categories` `/locations` `/industries` | Every filter value with its ID |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-iimjobs-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-iimjobs-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-iimjobs-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "product manager", "location": "Bangalore"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about IIMJobs Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20IIMJobs%20Scraper%20API.)

[![Ask Us by Email about IIMJobs Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20IIMJobs%20Scraper%20API&body=I%20need%20help%20using%20the%20IIMJobs%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Internshala Scraper**](https://github.com/omkarcloud/internshala-scraper) — Internshala internships & jobs: stipends, CTC, skills, applicants & employer profiles
- [**Hirist Scraper**](https://github.com/omkarcloud/hirist-scraper) — Hirist IT jobs, company ratings, recruiters & skills with live job counts
- [**Jobstreet Scraper**](https://github.com/omkarcloud/jobstreet-scraper) — JobStreet & JobsDB jobs, salaries, company reviews & career guides
- [**Cutshort Scraper**](https://github.com/omkarcloud/cutshort-scraper) — Cutshort India tech jobs, INR salary bands, skills & company profiles
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/iimjobs-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/iimjobs-scraper)
