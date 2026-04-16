"""Stages 3 + 4: Bio link aggregator detection and page scraping.

Detects whether a URL belongs to a known link aggregator, fetches the page,
and extracts all outbound links with their titles and surrounding text.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from loguru import logger

from pipeline.config import Config

# ---------------------------------------------------------------------------
# Aggregator registry
# ---------------------------------------------------------------------------

AGGREGATOR_REGISTRY: dict[str, str] = {
    "linktr.ee": "Linktree",
    "beacons.ai": "Beacons",
    "allmylinks.com": "AllMyLinks",
    "stan.store": "Stan.store",
    "snipfeed.co": "Snipfeed",
    "carrd.co": "Carrd",
    "bio.fm": "Bio.fm",
    "linkin.bio": "Linkin.bio",
    "linkpop.com": "Linkpop",
    "hoo.be": "Hoo.be",
    "komi.io": "Komi",
    "direct.me": "Direct.me",
    "withkoji.com": "Withkoji",
    "koji.to": "Withkoji",
    "campsite.bio": "Campsite",
    "tap.bio": "Tap.bio",
    "lnk.bio": "Lnk.bio",
    "shor.by": "Shorby",
    "solo.to": "Solo.to",
    "flow.page": "Flowpage",
}

# Domains where the aggregator uses subdomains (*.carrd.co, etc.)
WILDCARD_AGGREGATORS: dict[str, str] = {
    "carrd.co": "Carrd",
}

# Aggregators known to be JavaScript-heavy and need Playwright
JS_HEAVY_AGGREGATORS: set[str] = {
    "stan.store",
    "beacons.ai",
    "withkoji.com",
    "koji.to",
    "komi.io",
}

# Realistic user-agent pool for rotation
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ExtractedLink:
    url: str
    title: str = ""
    description: str = ""


@dataclass
class AggregatorResult:
    source_url: str
    aggregator_type: str  # name from registry, or "unknown" / "direct"
    links: list[ExtractedLink] = field(default_factory=list)
    bio_text: str = ""
    page_text: str = ""
    error: str | None = None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_aggregator(url: str) -> str | None:
    """Return the aggregator name if *url* is a known link aggregator, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return None

    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    # Exact match
    if domain in AGGREGATOR_REGISTRY:
        return AGGREGATOR_REGISTRY[domain]

    # Wildcard subdomain match (e.g. username.carrd.co)
    for base, name in WILDCARD_AGGREGATORS.items():
        if domain.endswith(f".{base}"):
            return name

    return None


def is_aggregator(url: str) -> bool:
    return detect_aggregator(url) is not None


# ---------------------------------------------------------------------------
# Fetching helpers
# ---------------------------------------------------------------------------

def _random_ua() -> str:
    return random.choice(USER_AGENTS)


def _random_delay(cfg: Config) -> None:
    time.sleep(random.uniform(cfg.request_delay_min, cfg.request_delay_max))


def _get_proxies(cfg: Config) -> dict[str, str] | None:
    if not cfg.proxy_urls:
        return None
    proxy = random.choice(cfg.proxy_urls)
    return {"http": proxy, "https": proxy}


def _fetch_with_requests(
    url: str,
    cfg: Config,
    *,
    max_retries: int = 3,
) -> str | None:
    """Fetch a page using ``requests`` with retries and backoff."""
    headers = {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=_get_proxies(cfg),
                timeout=20,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (429, 401, 403):
                wait = 2 ** (attempt + 1) + random.uniform(0, 1)
                logger.warning(
                    "HTTP {} for {} — backing off {:.1f}s (attempt {}/{})",
                    resp.status_code, url, wait, attempt + 1, max_retries,
                )
                time.sleep(wait)
                continue
            logger.warning("HTTP {} for {}", resp.status_code, url)
            return None
        except requests.RequestException as exc:
            wait = 2 ** (attempt + 1)
            logger.warning(
                "Request error for {} — {} (attempt {}/{})",
                url, exc, attempt + 1, max_retries,
            )
            time.sleep(wait)
    return None


def _fetch_with_playwright(url: str, cfg: Config) -> str | None:
    """Fetch a JS-heavy page using headless Chromium via Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error(
            "Playwright not installed. Install with: pip install playwright && playwright install chromium"
        )
        return None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=_random_ua(),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        logger.error("Playwright error for {}: {}", url, exc)
        return None


# ---------------------------------------------------------------------------
# HTML → links extraction
# ---------------------------------------------------------------------------

def _extract_links_from_html(html: str, base_url: str) -> list[ExtractedLink]:
    """Parse HTML and extract all outbound links with titles."""
    soup = BeautifulSoup(html, "lxml")
    links: list[ExtractedLink] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        resolved = urljoin(base_url, href)

        # Skip same-page / aggregator-internal links
        try:
            parsed = urlparse(resolved)
            base_parsed = urlparse(base_url)
            if parsed.netloc == base_parsed.netloc and parsed.path in ("", "/"):
                continue
        except Exception:
            pass

        if resolved in seen:
            continue
        seen.add(resolved)

        # Link title: anchor text, or title/aria-label attribute
        title = anchor.get_text(strip=True)
        if not title:
            title = anchor.get("title", "") or anchor.get("aria-label", "")

        # Description: nearby text (parent or sibling)
        description = ""
        parent = anchor.parent
        if parent:
            sibling_text = parent.get_text(strip=True)
            if sibling_text and sibling_text != title:
                description = sibling_text[:200]

        links.append(ExtractedLink(url=resolved, title=title, description=description))

    return links


def _extract_bio_text(html: str) -> str:
    """Pull bio / description text from common aggregator patterns."""
    soup = BeautifulSoup(html, "lxml")

    # Try meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    # Try OG description
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        return og["content"].strip()

    # Fallback: first <p> or <h1>/<h2> text
    for tag in ("h1", "h2", "p"):
        el = soup.find(tag)
        if el:
            text = el.get_text(strip=True)
            if len(text) > 10:
                return text[:300]

    return ""


def _extract_page_text(html: str) -> str:
    """Get all visible text from the page for keyword scanning."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace
    return re.sub(r"\s+", " ", text)[:2000]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scrape_aggregator_page(
    url: str,
    cfg: Config,
    *,
    force_playwright: bool = False,
) -> AggregatorResult:
    """Fetch an aggregator (or any) page and extract links + text.

    Uses requests+BS4 by default; falls back to Playwright for known
    JS-heavy aggregators or on explicit request.
    """
    aggregator_type = detect_aggregator(url) or "direct"

    if cfg.dry_run:
        logger.info("[DRY RUN] Would scrape: {} ({})", url, aggregator_type)
        return AggregatorResult(
            source_url=url,
            aggregator_type=aggregator_type,
        )

    # Decide fetch strategy
    parsed_domain = urlparse(url).netloc.lower().lstrip("www.")
    use_playwright = force_playwright or parsed_domain in JS_HEAVY_AGGREGATORS

    _random_delay(cfg)

    html: str | None = None
    if not use_playwright:
        html = _fetch_with_requests(url, cfg)

    if html is None and use_playwright:
        logger.info("Using Playwright for JS-heavy page: {}", url)
        html = _fetch_with_playwright(url, cfg)

    if html is None:
        return AggregatorResult(
            source_url=url,
            aggregator_type=aggregator_type,
            error="Failed to fetch page",
        )

    links = _extract_links_from_html(html, url)
    bio_text = _extract_bio_text(html)
    page_text = _extract_page_text(html)

    logger.debug(
        "Scraped {} — {} links found ({})", url, len(links), aggregator_type
    )

    return AggregatorResult(
        source_url=url,
        aggregator_type=aggregator_type,
        links=links,
        bio_text=bio_text,
        page_text=page_text,
    )
