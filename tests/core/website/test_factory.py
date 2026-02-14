"""Tests for WebsiteFactory URL routing."""

import pytest

from openlist_ani.core.website.aniapi import AniapiWebsite
from openlist_ani.core.website.common import CommonRSSWebsite
from openlist_ani.core.website.factory import WebsiteFactory
from openlist_ani.core.website.mikan import MikanWebsite


@pytest.fixture
def factory():
    return WebsiteFactory()


class TestWebsiteFactory:
    def test_create_mikan(self, factory):
        parser = factory.create("https://mikanani.me/RSS/Bangumi?bangumiId=123")
        assert isinstance(parser, MikanWebsite)

    def test_create_mikan_tv(self, factory):
        parser = factory.create("https://mikanime.tv/RSS/Bangumi")
        assert isinstance(parser, MikanWebsite)

    def test_create_aniapi(self, factory):
        parser = factory.create("https://api.ani.rip/ani-torrent.xml")
        assert isinstance(parser, AniapiWebsite)

    def test_create_common_fallback(self, factory):
        parser = factory.create("https://acg.rip/.xml")
        assert isinstance(parser, CommonRSSWebsite)

    def test_create_empty_url_raises(self, factory):
        with pytest.raises(ValueError, match="empty"):
            factory.create("")

    def test_create_invalid_url_raises(self, factory):
        with pytest.raises(ValueError):
            factory.create("not_a_url_without_scheme")

    def test_www_prefix_stripped(self, factory):
        parser = factory.create("https://www.mikanani.me/RSS")
        assert isinstance(parser, MikanWebsite)

    def test_subdomain_matching(self, factory):
        parser = factory.create("https://sub.api.ani.rip/feed.xml")
        assert isinstance(parser, AniapiWebsite)
