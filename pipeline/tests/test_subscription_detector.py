"""Tests for the subscription platform detector module."""

import pytest

from pipeline.subscription_detector import (
    detect_platform,
    detect_platforms,
    get_all_platform_domains,
    is_subscription_url,
)


class TestDetectPlatform:
    def test_onlyfans(self):
        match = detect_platform("https://onlyfans.com/someuser")
        assert match is not None
        assert match.platform_name == "OnlyFans"
        assert match.platform_domain == "onlyfans.com"
        assert match.username == "someuser"

    def test_onlyfans_www(self):
        match = detect_platform("https://www.onlyfans.com/creator123")
        assert match is not None
        assert match.platform_name == "OnlyFans"
        assert match.username == "creator123"

    def test_fansly(self):
        match = detect_platform("https://fansly.com/username")
        assert match is not None
        assert match.platform_name == "Fansly"
        assert match.username == "username"

    def test_manyvids(self):
        match = detect_platform("https://www.manyvids.com/Profile/123456/Username")
        assert match is not None
        assert match.platform_name == "ManyVids"

    def test_fanvue(self):
        match = detect_platform("https://fanvue.com/testuser")
        assert match is not None
        assert match.platform_name == "Fanvue"
        assert match.username == "testuser"

    def test_justforfans(self):
        match = detect_platform("https://justfor.fans/creator")
        assert match is not None
        assert match.platform_name == "JustForFans"
        assert match.username == "creator"

    def test_mym(self):
        match = detect_platform("https://mym.fans/somemodel")
        assert match is not None
        assert match.platform_name == "MYM"

    def test_loyalfans(self):
        match = detect_platform("https://loyalfans.com/user123")
        assert match is not None
        assert match.platform_name == "LoyalFans"

    def test_sextpanther(self):
        match = detect_platform("https://sextpanther.com/user")
        assert match is not None
        assert match.platform_name == "SextPanther"

    def test_not_a_platform(self):
        assert detect_platform("https://google.com") is None
        assert detect_platform("https://instagram.com/someone") is None
        assert detect_platform("https://twitter.com/user") is None

    def test_empty_url(self):
        assert detect_platform("") is None
        assert detect_platform(None) is None

    def test_url_without_scheme(self):
        match = detect_platform("onlyfans.com/user")
        assert match is not None
        assert match.platform_name == "OnlyFans"

    def test_non_username_paths_ignored(self):
        match = detect_platform("https://onlyfans.com/home")
        assert match is not None
        assert match.username is None  # "home" is not a username

    def test_username_extraction_with_prefix(self):
        # Some platforms use /u/ or /profile/ prefix
        match = detect_platform("https://fansly.com/u/testcreator")
        assert match is not None

    def test_username_with_special_chars(self):
        match = detect_platform("https://onlyfans.com/user_name.123")
        assert match is not None
        assert match.username == "user_name.123"


class TestDetectPlatforms:
    def test_multiple_urls(self):
        urls = [
            "https://onlyfans.com/creator1",
            "https://fansly.com/creator1",
            "https://google.com",
            "https://instagram.com/creator1",
        ]
        matches = detect_platforms(urls)
        assert len(matches) == 2
        platforms = {m.platform_name for m in matches}
        assert "OnlyFans" in platforms
        assert "Fansly" in platforms

    def test_deduplication_same_domain(self):
        urls = [
            "https://onlyfans.com/user1",
            "https://onlyfans.com/user2",
        ]
        matches = detect_platforms(urls)
        assert len(matches) == 1

    def test_empty_list(self):
        assert detect_platforms([]) == []


class TestIsSubscriptionUrl:
    def test_positive(self):
        assert is_subscription_url("https://onlyfans.com/user") is True

    def test_negative(self):
        assert is_subscription_url("https://google.com") is False


class TestGetAllPlatformDomains:
    def test_returns_set(self):
        domains = get_all_platform_domains()
        assert isinstance(domains, set)
        assert "onlyfans.com" in domains
        assert "www.onlyfans.com" in domains
        assert len(domains) >= 14  # At least all canonical domains
