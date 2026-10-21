"""Value helpers for the iimjobs parsers. Pure functions, no network; every
helper tolerates None and junk.

The generic helpers (safe nested access, numbers, the '*****' masks, text,
dates, lakh salaries, HTML -> text) have the same semantics as
hirist/shared.py — hirist.tech is iimjobs' sister board on the same job
service. They live here so the iimjobs package stands alone (it ships as
its own open-source repo, which must not pull in other sites' modules).
The rest is iimjobs-only: its links, UTC timestamps, the cleanups its
feeds need (experience suffixes in titles, ad-server-wrapped apply links,
placeholder logos) and the course fee / duration readers of iimjobs
Learning."""
import html as html_lib
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from iimjobs import refdata

# ---- safe access ---------------------------------------------------------------------------

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj

def as_list(value):
    return value if isinstance(value, list) else []

def as_dict(value):
    return value if isinstance(value, dict) else {}


# ---- numbers -------------------------------------------------------------------------------

def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN,
    the site's '*****' masks -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None

def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None

def count(value):
    """A non-negative count; negatives -> 0; the logged-out '*****' mask -> None."""
    out = to_int(value)
    if out is None:
        return None
    return out if out >= 0 else 0

def flag(value):
    """The site's 0/1 (also '0'/'1', true/false) -> bool; None stays None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes"):
            return True
        if low in ("false", "no", ""):
            return False
    out = to_int(value)
    return bool(out) if out is not None else None

def rating(value):
    """A 0-5 star rating rounded to 1 place; 0 / missing -> None."""
    out = num(value)
    return round(out, 1) if out else None

def year(value):
    """A founding / batch year: 4-digit int, else None (the site stores 0 for unknown)."""
    out = to_int(value)
    return out if out and 1000 <= out <= 2100 else None


# ---- text ----------------------------------------------------------------------------------

def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' / '*****' -> None."""
    if value is None or isinstance(value, bool):
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    if not out or set(out) == {"*"}:
        return None
    return out

def multiline(value):
    """Like text() but keeps line breaks (descriptions)."""
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None

def text_list(values):
    """A list of strings, trimmed, deduped, empties dropped."""
    out = []
    for value in as_list(values):
        item = text(value)
        if item and item not in out:
            out.append(item)
    return out

def split_list(value, sep=","):
    """'Chennai,Tamil Nadu,India' / 'Pune/Indore' -> ['Chennai', 'Tamil Nadu', 'India']."""
    if isinstance(value, list):
        return text_list(value)
    value = text(value)
    if not value:
        return []
    return text_list(value.split(sep))

def slugify(value):
    """'Backend Development' -> 'backend-development'."""
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or None


IST = timezone(timedelta(hours=5, minutes=30))

_LONG_DATE_FORMATS = ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%d/%m/%Y")

def iso_date(value):
    """'2026-10-12' / '2026-10-12T…' / 'October 12, 2026' -> 'YYYY-MM-DD'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return "-".join(match.groups())
    for fmt in _LONG_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

def website(value):
    """'www.squarerootindia.com' / 'https://x.com' -> an https link; '' -> None."""
    value = text(value)
    if not value:
        return None
    if value.startswith(("http://", "https://")):
        return value
    return "https://" + value.lstrip("/")

def salary(min_lakhs, max_lakhs, hidden):
    """The site quotes salaries in lakhs per annum and most recruiters hide
    them (hideSal=1 with min/max 0) -> {min, max (INR per year), min_lakhs,
    max_lakhs, currency, period, is_disclosed}."""
    lo, hi = num(min_lakhs), num(max_lakhs)
    disclosed = not flag(hidden) and bool(lo or hi)
    if not disclosed:
        lo = hi = None
    return {
        "min": int(round(lo * refdata.LAKH)) if lo else None,
        "max": int(round(hi * refdata.LAKH)) if hi else None,
        "min_lakhs": lo,
        "max_lakhs": hi,
        "currency": refdata.DEFAULT_CURRENCY,
        "period": "year",
        "is_disclosed": disclosed,
    }


# ---- HTML -> text ----------------------------------------------------------------------------

_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}

_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}

class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")      # a list ends its paragraph
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()   # list items stay tight
    return out or None

def html_fragment(value):
    """The job description as the site stores it (an HTML fragment); '' / None -> None."""
    value = value if isinstance(value, str) else None
    if not value or not value.strip():
        return None
    return value.strip()


# ---- dates -------------------------------------------------------------------------------------

def _from_ms(value):
    ms = num(value)
    if not ms or ms < 10 ** 11:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def utc_datetime_ms(value):
    """Epoch milliseconds -> '2026-10-14T03:45:37Z' (UTC, second precision); junk -> None."""
    stamp = _from_ms(value)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None


def site_date_ms(value):
    """Epoch milliseconds -> the calendar date the site shows (India time), '2026-10-14'."""
    stamp = _from_ms(value)
    return stamp.astimezone(IST).strftime("%Y-%m-%d") if stamp else None


def utc_datetime(value):
    """'2026-09-30T04:31:49.000+00:00' / '2024-11-19T12:28:36.000Z' -> '2026-09-30T04:31:49Z'."""
    value = text(value)
    if not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return iso_date(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- links -------------------------------------------------------------------------------------

_SITE_HOST = re.compile(r"^https?://(?:www\.)?iimjobs\.(?:com|tech)(?=/|$)", re.I)


def link(path):
    """A site-relative path or absolute URL -> an absolute https link; the
    site's http:// and iimjobs.tech spellings -> https://www.iimjobs.com."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    if _SITE_HOST.match(path):
        return refdata.BASE_URL + _SITE_HOST.sub("", path)
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return f"{refdata.BASE_URL}/{path.lstrip('/')}"


def job_link(job_id, title=None):
    """The canonical /j/<slug>-<id> link of a job."""
    job_id = to_int(job_id)
    if not job_id:
        return None
    slug = slugify(title)
    return f"{refdata.BASE_URL}/j/{slug + '-' if slug else ''}{job_id}"


def job_id_from_link(value):
    """'https://www.iimjobs.com/j/piramal-product-manager-1740408' -> 1740408."""
    value = text(value)
    if not value:
        return None
    match = re.search(r"/j/(?:[^/?#]*?-)?(\d+)(?:[/?#]|$)", value)
    return int(match.group(1)) if match else None


def company_link(slug):
    return f"{refdata.BASE_URL}/{slug}-careers" if slug else None


def recruiter_link(recruiter_id, name=None):
    recruiter_id = to_int(recruiter_id)
    if not recruiter_id:
        return None
    slug = slugify(name)
    return f"{refdata.BASE_URL}/r/{recruiter_id}{'-' + slug if slug else ''}"


def category_link(slug):
    return f"{refdata.BASE_URL}/c/{slug}" if slug else None


def skill_link(name):
    slug = slugify(name)
    return f"{refdata.BASE_URL}/k/{slug}-jobs" if slug else None


def course_link(course_id, title=None):
    """The course page: /course/<Title-With-Dashes>-<id> (the title URL-encoded, as the site spells it)."""
    course_id = to_int(course_id)
    if not course_id:
        return None
    title = text(title)
    if not title:
        return f"{refdata.BASE_URL}/course/{course_id}"
    return f"{refdata.BASE_URL}/course/{quote('-'.join(title.split()), safe='-')}-{course_id}"


# ---- cleanups ------------------------------------------------------------------------------------

_EXPERIENCE_SUFFIX = re.compile(r"\s*\(\s*\d+\s*-\s*\d+\s*yrs?\.?\s*\)\s*$", re.I)


def job_title(value):
    """'NIIT - Sales Specialist (5-8 yrs)' -> 'NIIT - Sales Specialist': the
    women's feed appends the experience band (the card carries it apart)."""
    value = text(value)
    if not value:
        return None
    return _EXPERIENCE_SUFFIX.sub("", value).strip() or value


_PLACEHOLDER_LOGO = re.compile(r"/centralised-0\.\w+$")
_CENTRALISED_LOGO = re.compile(r"/CompanyLogos/centralised-(\d+)\.\w+$", re.I)


def logo(value):
    """A company logo link; '' and the `centralised-0` placeholder -> None."""
    value = link(value)
    if not value or _PLACEHOLDER_LOGO.search(value):
        return None
    return value


def company_id_from_logo(value):
    """The site files company logos as CompanyLogos/centralised-<companyId>.webp;
    the feeds without a recruiter block (skill / category feeds) carry only
    the logo, so the company id is read back from it. 0 / none -> None."""
    match = _CENTRALISED_LOGO.search(str(value or ""))
    company_id = int(match.group(1)) if match else 0
    return company_id or None


_TRACKING_PARAM = re.compile(r"^(utm_|gclid$|fbclid$|dclid$)", re.I)


def apply_link(value):
    """An external apply link without the ad-server wrapper
    ('https://ad.doubleclick.net/ddm/clk/…?https://careers.x.com/job/1?utm_source=…')
    and without utm_* / click-id params; '' -> None."""
    value = text(value)
    if not value:
        return None
    if "doubleclick.net/" in value and "?http" in value:
        value = value[value.index("?http") + 1:]
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return link(value)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not _TRACKING_PARAM.match(k)]
    return urlunparse(parsed._replace(query=urlencode(query, safe=":/"), fragment=""))


def person(value):
    """'Shveta Verma<br>\\nInclusion and Diversity Leader' -> ('Shveta Verma', 'Inclusion and Diversity Leader')."""
    if not isinstance(value, str) or not value.strip():
        return None, None
    parts = [text(p) for p in re.split(r"<br\s*/?>|\n", value, flags=re.I)]
    parts = [p for p in parts if p]
    if not parts:
        return None, None
    return parts[0], (", ".join(parts[1:]) or None)


def rich_text(value):
    """An HTML block that may be empty markup ('<p></p>') -> (html, text) or (None, None)."""
    html = html_fragment(value)
    plain = html_to_text(html) if html else None
    if not plain:
        return None, None
    return html, plain


# ---- iimjobs Learning: fees, durations --------------------------------------------------------------

_AMOUNT = re.compile(r"\d[\d,.]*(?![\d,.]*\s*%)")      # a number that is not a percentage ('30% scholarships')


def _amount(token, multiplier):
    token = token.strip(".,")
    if "." in token and "," in token and token.index(".") < token.index(","):
        token = token.replace(".", "")        # 'INR 2.50,000' — a mistyped thousands separator
    token = token.replace(",", "")
    try:
        value = float(token)
    except ValueError:
        return None
    if value < 100 and multiplier == 1:
        return None                            # a bare '2' without a unit is not a fee
    return int(round(value * multiplier))


def course_fee(value):
    """'INR 1,40,000 + GST' / '₹2,74,000 + GST' / '1.5 to 2.8 lakhs' ->
    {text, min, max, currency, is_gst_extra}; unparseable amounts stay in `text`."""
    raw = text(value)
    if not raw:
        return {"text": None, "min": None, "max": None, "currency": None, "is_gst_extra": None}
    low = raw.lower()
    multiplier = 10_000_000 if "crore" in low else refdata.LAKH if re.search(r"lakh|lac\b|\blpa\b", low) else 1
    amounts = [a for a in (_amount(t, multiplier) for t in _AMOUNT.findall(raw)) if a]
    currency = "USD" if ("$" in raw or "usd" in low) else refdata.DEFAULT_CURRENCY if amounts else None
    return {"text": raw, "min": min(amounts) if amounts else None, "max": max(amounts) if amounts else None,
            "currency": currency, "is_gst_extra": "gst" in low}


_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(year|yr|month|mon|week|wk|day)", re.I)
_UNIT_MONTHS = {"year": 12, "yr": 12, "month": 1, "mon": 1, "week": 12 / 52, "wk": 12 / 52, "day": 12 / 365}


def duration_months(value):
    """'6 Months' -> 6, '2 Years' -> 24, '35 Weeks' -> 8.1; unparseable -> None."""
    match = _DURATION.search(str(value or ""))
    if not match:
        return None
    months = float(match.group(1)) * _UNIT_MONTHS[match.group(2).lower()]
    return int(months) if months.is_integer() else round(months, 1)


def labels(values):
    """A label list, trimmed, deduped without regard to case ('FinTech Companies'
    and 'Fintech Companies' are one label; the first spelling wins)."""
    out, seen = [], set()
    for value in text_list(values):
        if value.lower() not in seen:
            seen.add(value.lower())
            out.append(value)
    return out


def ids_from_csv(value):
    """'2,13,14' / [2, 13, 14] / '80 96 433' -> [2, 13, 14]."""
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[,\s]+", str(value or ""))
    out = []
    for item in items:
        number = to_int(item)
        if number and number > 0 and number not in out:
            out.append(number)
    return out
