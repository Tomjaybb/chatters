"""Tests for the keyword detector module."""

import pytest

from pipeline.keyword_detector import (
    KeywordMatch,
    KeywordResult,
    calculate_confidence,
    detect_keywords,
    scan_text,
)


class TestScanText:
    def test_direct_keyword_match(self):
        matches = scan_text("Check out my exclusive content here")
        assert any(m.keyword == "exclusive content" for m in matches)
        assert any(m.category == "direct" for m in matches)

    def test_direct_keyword_case_insensitive(self):
        matches = scan_text("NSFW warning on this page")
        assert any(m.keyword == "nsfw" for m in matches)

    def test_18_plus(self):
        matches = scan_text("Must be 18+ to view")
        assert any(m.keyword == "18+" for m in matches)

    def test_soft_keyword_match(self):
        matches = scan_text("Subscribe to me for more")
        assert any(m.keyword == "subscribe to me" for m in matches)
        assert any(m.category == "soft" for m in matches)

    def test_platform_adjacent_OF(self):
        # "OF" should match case-sensitively (uppercase only)
        matches = scan_text("Link to my OF below")
        assert any(m.keyword == "OF" for m in matches)

    def test_platform_adjacent_OF_no_false_positive(self):
        # Lowercase "of" should NOT match
        matches = scan_text("I took a photo of the sunset")
        assert not any(m.keyword == "OF" for m in matches)

    def test_zero_F_evasion(self):
        matches = scan_text("Find me on 0F")
        assert any(m.keyword == "0F" for m in matches)

    def test_emoji_with_companion(self):
        matches = scan_text("Click the link below 🔥🍑")
        assert any(m.category == "emoji" for m in matches)

    def test_emoji_without_companion_no_match(self):
        matches = scan_text("Beautiful sunset 🔥")
        assert not any(m.category == "emoji" for m in matches)

    def test_no_matches(self):
        matches = scan_text("Just a normal photography portfolio")
        assert matches == []

    def test_empty_text(self):
        assert scan_text("") == []

    def test_multiple_categories(self):
        text = "Exclusive content on my OF page. Subscribe to me! 🌶️ link below"
        matches = scan_text(text)
        categories = {m.category for m in matches}
        assert "direct" in categories
        assert "platform_adjacent" in categories
        assert "soft" in categories

    def test_word_boundary_no_false_positive(self):
        # "vip" inside "viper" should NOT match
        matches = scan_text("I love my pet viper snake")
        assert not any(m.keyword == "vip content" for m in matches)

    def test_spicy_links(self):
        matches = scan_text("spicy links in my bio")
        assert any(m.keyword == "spicy links" for m in matches)

    def test_uncensored(self):
        matches = scan_text("See my uncensored photos")
        assert any(m.keyword == "uncensored" for m in matches)

    def test_adults_only(self):
        matches = scan_text("Adults only content")
        assert any(m.keyword == "adults only" for m in matches)

    def test_members_only(self):
        matches = scan_text("Members only access")
        assert any(m.keyword == "members only" for m in matches)

    def test_context_extraction(self):
        text = "Hello world, check my exclusive content for fans here please"
        matches = scan_text(text)
        match = next(m for m in matches if m.keyword == "exclusive content")
        assert "exclusive content" in match.context


class TestCalculateConfidence:
    def test_subscription_link_is_100(self):
        score = calculate_confidence([], has_subscription_link=True)
        assert score == 100

    def test_no_matches_is_zero(self):
        assert calculate_confidence([]) == 0

    def test_multiple_direct_keywords(self):
        matches = [
            KeywordMatch(keyword="nsfw", category="direct"),
            KeywordMatch(keyword="exclusive content", category="direct"),
        ]
        score = calculate_confidence(matches)
        assert score >= 80

    def test_single_direct_keyword(self):
        matches = [KeywordMatch(keyword="nsfw", category="direct")]
        score = calculate_confidence(matches)
        assert score >= 70

    def test_soft_plus_emoji(self):
        matches = [
            KeywordMatch(keyword="subscribe to me", category="soft"),
            KeywordMatch(keyword="🔥", category="emoji"),
        ]
        score = calculate_confidence(matches)
        assert score >= 60

    def test_single_soft_keyword(self):
        matches = [KeywordMatch(keyword="fan page", category="soft")]
        score = calculate_confidence(matches)
        assert score == 30

    def test_platform_adjacent(self):
        matches = [KeywordMatch(keyword="OF", category="platform_adjacent")]
        score = calculate_confidence(matches)
        assert score >= 65

    def test_stacking_bonus(self):
        matches = [
            KeywordMatch(keyword="nsfw", category="direct"),
            KeywordMatch(keyword="OF", category="platform_adjacent"),
        ]
        score = calculate_confidence(matches)
        assert score > 70  # Base 70 + bonus

    def test_capped_at_95(self):
        matches = [
            KeywordMatch(keyword="nsfw", category="direct"),
            KeywordMatch(keyword="18+", category="direct"),
            KeywordMatch(keyword="OF", category="platform_adjacent"),
            KeywordMatch(keyword="🔥", category="emoji"),
            KeywordMatch(keyword="subscribe to me", category="soft"),
        ]
        score = calculate_confidence(matches)
        assert score <= 95


class TestDetectKeywords:
    def test_multiple_texts(self):
        texts = ["Check my exclusive content", "Subscribe to me for more"]
        result = detect_keywords(texts)
        assert isinstance(result, KeywordResult)
        assert len(result.matches) >= 2
        assert result.confidence_score > 0

    def test_with_subscription_link(self):
        result = detect_keywords(["normal bio text"], has_subscription_link=True)
        assert result.confidence_score == 100

    def test_deduplication(self):
        texts = ["NSFW content", "More NSFW content here"]
        result = detect_keywords(texts)
        nsfw_matches = [m for m in result.matches if m.keyword == "nsfw"]
        assert len(nsfw_matches) == 1

    def test_status_confirmed(self):
        result = detect_keywords(["test"], has_subscription_link=True)
        # Score 100 → status based on score
        assert result.confidence_score == 100

    def test_status_unlikely(self):
        result = detect_keywords(["just a normal bio"])
        assert result.status == "unlikely"
        assert result.confidence_score == 0

    def test_matched_keywords_property(self):
        result = detect_keywords(["my exclusive content is NSFW"])
        assert "exclusive content" in result.matched_keywords
        assert "nsfw" in result.matched_keywords
