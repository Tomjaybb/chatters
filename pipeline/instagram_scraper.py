"""Stage 2: Instagram following-list scraper with pluggable providers.

Supports three backends:
  - instaloader (default, open-source, uses IG session cookies)
  - apify       (Apify Instagram Scraper actor, paid API)
  - instagrapi  (unofficial IG private API wrapper)

The provider is swappable via config so if one gets rate-limited you can
fall back to another without changing pipeline code.
"""

from __future__ import annotations

import abc
import random
import time
from dataclasses import dataclass
from typing import Any

from loguru import logger

from pipeline.config import Config

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class IGProfile:
    username: str
    display_name: str = ""
    follower_count: int = 0
    bio_text: str = ""
    bio_link: str = ""
    profile_pic_url: str = ""
    is_verified: bool = False
    is_business: bool = False


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class IGProvider(abc.ABC):
    """Base class for Instagram scraping backends."""

    name: str = "base"

    @abc.abstractmethod
    def login(self, cfg: Config) -> None: ...

    @abc.abstractmethod
    def get_following(self, handle: str, cfg: Config) -> list[IGProfile]: ...

    @abc.abstractmethod
    def validate_handle(self, handle: str, cfg: Config) -> bool: ...


# ---------------------------------------------------------------------------
# Instaloader provider
# ---------------------------------------------------------------------------

class InstaloadProvider(IGProvider):
    name = "instaloader"

    def __init__(self) -> None:
        self._loader: Any = None

    def login(self, cfg: Config) -> None:
        try:
            import instaloader
        except ImportError:
            raise RuntimeError(
                "instaloader not installed. Run: pip install instaloader"
            )
        self._loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )
        if cfg.ig_username and cfg.ig_password:
            try:
                self._loader.login(cfg.ig_username, cfg.ig_password)
                logger.info("Instaloader logged in as {}", cfg.ig_username)
            except Exception as exc:
                logger.error("Instaloader login failed: {}", exc)
                raise

    def validate_handle(self, handle: str, cfg: Config) -> bool:
        import instaloader
        try:
            instaloader.Profile.from_username(self._loader.context, handle)
            return True
        except instaloader.exceptions.ProfileNotExistsException:
            return False
        except Exception as exc:
            logger.warning("Could not validate {}: {}", handle, exc)
            return False

    def get_following(self, handle: str, cfg: Config) -> list[IGProfile]:
        import instaloader

        try:
            profile = instaloader.Profile.from_username(
                self._loader.context, handle
            )
        except Exception as exc:
            logger.error("Failed to load profile {}: {}", handle, exc)
            return []

        profiles: list[IGProfile] = []
        try:
            for followee in profile.get_followees():
                # Rate limiting
                time.sleep(1.0 / cfg.ig_max_rps + random.uniform(0, 0.5))

                profiles.append(IGProfile(
                    username=followee.username,
                    display_name=followee.full_name or "",
                    follower_count=followee.followers,
                    bio_text=followee.biography or "",
                    bio_link=followee.external_url or "",
                    profile_pic_url=followee.profile_pic_url or "",
                    is_verified=followee.is_verified,
                    is_business=getattr(followee, "is_business_account", False),
                ))
                logger.debug("  → {}", followee.username)
        except Exception as exc:
            logger.error(
                "Error fetching followees for {} (got {} so far): {}",
                handle, len(profiles), exc,
            )

        return profiles


# ---------------------------------------------------------------------------
# Apify provider
# ---------------------------------------------------------------------------

class ApifyProvider(IGProvider):
    name = "apify"

    def login(self, cfg: Config) -> None:
        if not cfg.apify_api_key:
            raise RuntimeError("APIFY_API_KEY not set in config")
        try:
            from apify_client import ApifyClient
            self._client = ApifyClient(cfg.apify_api_key)
        except ImportError:
            raise RuntimeError(
                "apify-client not installed. Run: pip install apify-client"
            )

    def validate_handle(self, handle: str, cfg: Config) -> bool:
        # Apify doesn't have a cheap validate — assume valid
        return True

    def get_following(self, handle: str, cfg: Config) -> list[IGProfile]:
        actor_input = {
            "username": [handle],
            "resultsType": "following",
            "resultsLimit": 5000,
        }
        try:
            run = self._client.actor("apify/instagram-scraper").call(
                run_input=actor_input
            )
            items = list(
                self._client.dataset(run["defaultDatasetId"]).iterate_items()
            )
        except Exception as exc:
            logger.error("Apify scraper failed for {}: {}", handle, exc)
            return []

        profiles: list[IGProfile] = []
        for item in items:
            profiles.append(IGProfile(
                username=item.get("username", ""),
                display_name=item.get("fullName", ""),
                follower_count=item.get("followersCount", 0),
                bio_text=item.get("biography", ""),
                bio_link=item.get("externalUrl", ""),
                profile_pic_url=item.get("profilePicUrl", ""),
                is_verified=item.get("verified", False),
                is_business=item.get("isBusinessAccount", False),
            ))
        return profiles


# ---------------------------------------------------------------------------
# Instagrapi provider
# ---------------------------------------------------------------------------

class InstagrapiProvider(IGProvider):
    name = "instagrapi"

    def __init__(self) -> None:
        self._client: Any = None

    def login(self, cfg: Config) -> None:
        try:
            from instagrapi import Client
        except ImportError:
            raise RuntimeError(
                "instagrapi not installed. Run: pip install instagrapi"
            )
        self._client = Client()
        if cfg.proxy_urls:
            self._client.set_proxy(cfg.proxy_urls[0])
        if cfg.ig_username and cfg.ig_password:
            try:
                self._client.login(cfg.ig_username, cfg.ig_password)
                logger.info("Instagrapi logged in as {}", cfg.ig_username)
            except Exception as exc:
                logger.error("Instagrapi login failed: {}", exc)
                raise

    def validate_handle(self, handle: str, cfg: Config) -> bool:
        try:
            self._client.user_info_by_username(handle)
            return True
        except Exception:
            return False

    def get_following(self, handle: str, cfg: Config) -> list[IGProfile]:
        try:
            user_id = self._client.user_id_from_username(handle)
            followees = self._client.user_following(user_id)
        except Exception as exc:
            logger.error("Instagrapi failed for {}: {}", handle, exc)
            return []

        profiles: list[IGProfile] = []
        for uid, info in followees.items():
            time.sleep(1.0 / cfg.ig_max_rps + random.uniform(0, 0.5))
            profiles.append(IGProfile(
                username=info.username,
                display_name=info.full_name or "",
                follower_count=info.follower_count or 0,
                bio_text=getattr(info, "biography", "") or "",
                bio_link=getattr(info, "external_url", "") or "",
                profile_pic_url=str(info.profile_pic_url or ""),
                is_verified=getattr(info, "is_verified", False),
                is_business=getattr(info, "is_business", False),
            ))
        return profiles


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[IGProvider]] = {
    "instaloader": InstaloadProvider,
    "apify": ApifyProvider,
    "instagrapi": InstagrapiProvider,
}


def get_provider(name: str) -> IGProvider:
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown IG provider '{name}'. Choose from: {list(_PROVIDERS)}"
        )
    return cls()


def scrape_agency_following(
    handle: str,
    cfg: Config,
    provider: IGProvider | None = None,
) -> list[IGProfile]:
    """High-level helper: scrape a single agency's following list."""
    if provider is None:
        provider = get_provider(cfg.ig_provider)
        provider.login(cfg)

    if cfg.dry_run:
        logger.info("[DRY RUN] Would scrape following list for @{}", handle)
        return []

    logger.info("Scraping following list for @{} via {}", handle, provider.name)
    profiles = provider.get_following(handle, cfg)
    logger.info("  → {} accounts found", len(profiles))
    return profiles
