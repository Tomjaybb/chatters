"""Tests for the aggregator detection logic in aggregator_scraper."""

import pytest

from pipeline.aggregator_scraper import (
    AGGREGATOR_REGISTRY,
    ExtractedLink,
    _extract_links_from_html,
    _extract_bio_text,
    _extract_page_text,
    detect_aggregator,
    is_aggregator,
)


class TestDetectAggregator:
    def test_linktree(self):
        assert detect_aggregator("https://linktr.ee/someuser") == "Linktree"

    def test_beacons(self):
        assert detect_aggregator("https://beacons.ai/creator") == "Beacons"

    def test_allmylinks(self):
        assert detect_aggregator("https://allmylinks.com/user") == "AllMyLinks"

    def test_stan_store(self):
        assert detect_aggregator("https://stan.store/creator") == "Stan.store"

    def test_snipfeed(self):
        assert detect_aggregator("https://snipfeed.co/user") == "Snipfeed"

    def test_carrd_direct(self):
        assert detect_aggregator("https://carrd.co/user") == "Carrd"

    def test_carrd_subdomain(self):
        assert detect_aggregator("https://mysite.carrd.co") == "Carrd"

    def test_bio_fm(self):
        assert detect_aggregator("https://bio.fm/user") == "Bio.fm"

    def test_linkinbio(self):
        assert detect_aggregator("https://linkin.bio/creator") == "Linkin.bio"

    def test_linkpop(self):
        assert detect_aggregator("https://linkpop.com/user") == "Linkpop"

    def test_hoobe(self):
        assert detect_aggregator("https://hoo.be/someone") == "Hoo.be"

    def test_withkoji(self):
        assert detect_aggregator("https://withkoji.com/@user") == "Withkoji"

    def test_koji_alias(self):
        assert detect_aggregator("https://koji.to/user") == "Withkoji"

    def test_direct_me(self):
        assert detect_aggregator("https://direct.me/user") == "Direct.me"

    def test_not_aggregator(self):
        assert detect_aggregator("https://google.com") is None
        assert detect_aggregator("https://instagram.com/user") is None
        assert detect_aggregator("https://onlyfans.com/user") is None

    def test_empty_url(self):
        assert detect_aggregator("") is None
        assert detect_aggregator(None) is None

    def test_without_scheme(self):
        assert detect_aggregator("linktr.ee/user") == "Linktree"

    def test_www_prefix_stripped(self):
        assert detect_aggregator("https://www.linktr.ee/user") == "Linktree"


class TestIsAggregator:
    def test_true(self):
        assert is_aggregator("https://linktr.ee/user") is True

    def test_false(self):
        assert is_aggregator("https://google.com") is False


class TestExtractLinksFromHTML:
    def test_basic_extraction(self):
        html = """
        <html><body>
          <a href="https://onlyfans.com/creator1">My OnlyFans</a>
          <a href="https://fansly.com/creator1">My Fansly</a>
          <a href="https://twitter.com/creator1">Twitter</a>
        </body></html>
        """
        links = _extract_links_from_html(html, "https://linktr.ee/test")
        assert len(links) == 3
        assert any(l.url == "https://onlyfans.com/creator1" for l in links)
        assert any(l.title == "My OnlyFans" for l in links)

    def test_skips_javascript_and_mailto(self):
        html = """
        <html><body>
          <a href="javascript:void(0)">Click</a>
          <a href="mailto:test@test.com">Email</a>
          <a href="tel:+1234567890">Call</a>
          <a href="https://example.com">Real link</a>
        </body></html>
        """
        links = _extract_links_from_html(html, "https://test.com")
        assert len(links) == 1
        assert links[0].url == "https://example.com"

    def test_deduplication(self):
        html = """
        <html><body>
          <a href="https://example.com/page">Link 1</a>
          <a href="https://example.com/page">Link 2</a>
        </body></html>
        """
        links = _extract_links_from_html(html, "https://test.com")
        assert len(links) == 1

    def test_relative_url_resolution(self):
        html = '<html><body><a href="/page">Link</a></body></html>'
        links = _extract_links_from_html(html, "https://example.com")
        assert links[0].url == "https://example.com/page"

    def test_title_from_attribute(self):
        html = '<html><body><a href="https://example.com" title="My Link"></a></body></html>'
        links = _extract_links_from_html(html, "https://test.com")
        assert links[0].title == "My Link"

    def test_empty_html(self):
        links = _extract_links_from_html("<html><body></body></html>", "https://test.com")
        assert links == []


class TestExtractBioText:
    def test_meta_description(self):
        html = '<html><head><meta name="description" content="Model & creator 🌶️"></head><body></body></html>'
        bio = _extract_bio_text(html)
        assert "creator" in bio

    def test_og_description(self):
        html = '<html><head><meta property="og:description" content="Find all my links here"></head><body></body></html>'
        bio = _extract_bio_text(html)
        assert "links" in bio

    def test_fallback_to_h1(self):
        html = "<html><body><h1>Welcome to my page with lots of content</h1></body></html>"
        bio = _extract_bio_text(html)
        assert "Welcome" in bio


class TestExtractPageText:
    def test_strips_scripts(self):
        html = """
        <html><body>
          <script>var x = 1;</script>
          <p>Visible text here</p>
          <style>.hidden{}</style>
        </body></html>
        """
        text = _extract_page_text(html)
        assert "Visible text" in text
        assert "var x" not in text
        assert ".hidden" not in text

    def test_max_length(self):
        long_text = "A" * 5000
        html = f"<html><body><p>{long_text}</p></body></html>"
        text = _extract_page_text(html)
        assert len(text) <= 2000
