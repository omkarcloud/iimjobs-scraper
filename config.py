"""Configuration for the IIMJobs Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT           port the API listens on (default 8000)
    IIMJOBS_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                   (default: none — direct). iimjobs' job service and its
                   course service answer plain HTTP with no cookies, so you
                   very likely don't need this. Set it only if you start
                   seeing failures at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

IIMJOBS_PROXY = os.environ.get("IIMJOBS_PROXY") or None

# Names the iimjobs package reads.
IIMJOBS_PROXY_COUNTRY = None             # unused here: IIMJOBS_PROXY above is the whole proxy policy
IIMJOBS_MAX_ATTEMPTS = MAX_RETRIES       # attempts per upstream call
IIMJOBS_WORKERS = 6                      # parallel upstream calls in batch, include_details and company search


def iimjobs_proxy(fallback=False):
    """The proxy for one iimjobs request: IIMJOBS_PROXY, or None for direct."""
    return os.environ.get("IIMJOBS_PROXY") or None
