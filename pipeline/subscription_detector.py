"""Stage 5: Subscription platform detection.

Maintains a registry of paid subscription platform domains, matches destination
URLs against them, and extracts creator usernames from URL paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Platform registry
# ---------------------------------------------------------------------------

# Maps canonical domain → display name
PLATFORM_REGISTRY: dict[str, str] = {
    "onlyfans.com": "OnlyFans",
    "fansly.com": "Fansly",
    "manyvids.com": "ManyVids",
    "fanvue.com": "Fanvue",
    "fancentro.com": "FanCentro",
    "justfor.fans": "JustForFans",
    "mym.fans": "MYM",
    "loyalfans.com": "LoyalFans",
    "scrileconnect.com": "Scrile Connect",
    "admireme.vip": "AdmireMe",
    "ifans.com": "iFans",
    "friends2follow.com": "Friends2Follow",
    "frisk.chat": "Frisk",
    "sextpanther.com": "SextPanther",
}

# Alternate / shortlink domains that redirect to the canonical ones
DOMAIN_ALIASES: dict[str, str] = {
    "www.onlyfans.com": "onlyfans.com",
    "www.fansly.com": "fansly.com",
    "www.manyvids.com": "manyvids.com",
    "www.fanvue.com": "fanvue.com",
    "www.fancentro.com": "fancentro.com",
    "www.loyalfans.com": "loyalfans.com",
    "www.ifans.com": "ifans.com",
    "www.frisk.chat": "frisk.chat",
    "www.sextpanther.com": "sextpanther.com",
}

# Path segments that are NOT usernames (common site pages)
_NON_USERNAME_PATHS = frozenset({
    "", "home", "about", "terms", "privacy", "faq", "help", "support",
    "explore", "search", "login", "signup", "register", "pricing",
    "creators", "categories", "blog",
})


@dataclass
class PlatformMatch:
    platform_name: str
    platform_domain: str
    url: str
    username: str | None = None


def _normalise_domain(raw: str) -> str:
    """Lowercase and strip ``www.`` prefix."""
    d = raw.lower().strip()
    return DOMAIN_ALIASES.get(d, d)


def _extract_username(path: str) -> str | None:
    """Try to pull a username from the first meaningful URL path segment."""
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        return None
    candidate = segments[0].lower()
    # Strip common prefixes some platforms use  (e.g. /u/username)
    if candidate in ("u", "profile", "user", "c", "creator") and len(segments) > 1:
        candidate = segments[1].lower()
    if candidate in _NON_USERNAME_PATHS:
        return None
    # Usernames are typically alphanumeric + underscores/dots
    if re.fullmatch(r"[a-z0-9_.@-]+", candidate):
        return candidate
    return None


def detect_platform(url: str) -> PlatformMatch | None:
    """Check whether *url* belongs to a known subscription platform.

    Returns a ``PlatformMatch`` if the domain matches, else ``None``.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return None

    domain = _normalise_domain(parsed.netloc)

    if domain in PLATFORM_REGISTRY:
        return PlatformMatch(
            platform_name=PLATFORM_REGISTRY[domain],
            platform_domain=domain,
            url=url,
            username=_extract_username(parsed.path),
        )
    return None


def detect_platforms(urls: list[str]) -> list[PlatformMatch]:
    """Check a list of URLs and return all subscription platform matches."""
    results: list[PlatformMatch] = []
    seen_domains: set[str] = set()
    for url in urls:
        match = detect_platform(url)
        if match and match.platform_domain not in seen_domains:
            seen_domains.add(match.platform_domain)
            results.append(match)
    return results


def is_subscription_url(url: str) -> bool:
    """Quick boolean check — is this URL a known subscription platform?"""
    return detect_platform(url) is not None


def get_all_platform_domains() -> set[str]:
    """Return the full set of domains (canonical + aliases) we watch for."""
    domains = set(PLATFORM_REGISTRY.keys())
    domains.update(DOMAIN_ALIASES.keys())
    return domains
