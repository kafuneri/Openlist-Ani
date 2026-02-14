"""Tests for MikanWebsite entry parsing and season extraction."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openlist_ani.core.website.mikan import MikanWebsite


@pytest.fixture
def mikan():
    return MikanWebsite()


class TestMikanWebsite:
    def test_split_name_season_basic(self, mikan):
        name, season = mikan._split_anime_name_and_season("我推的孩子 第二季")
        assert name == "我推的孩子"
        assert season == 2

    def test_split_name_season_no_season(self, mikan):
        name, season = mikan._split_anime_name_and_season("我独自升级")
        assert name == "我独自升级"
        assert season == 1

    def test_split_name_season_empty_string(self, mikan):
        """Empty string must not crash."""
        name, season = mikan._split_anime_name_and_season("")
        assert name == ""
        assert season == 1

    def test_split_name_season_none_input(self, mikan):
        """None input must not crash (coredump prevention)."""
        name, season = mikan._split_anime_name_and_season(None)
        assert name == ""
        assert season == 1

    def test_parse_cn_number_arabic(self, mikan):
        assert mikan._parse_cn_number("3") == 3

    def test_parse_cn_number_chinese(self, mikan):
        assert mikan._parse_cn_number("三") == 3
        assert mikan._parse_cn_number("十") == 10
        assert mikan._parse_cn_number("十二") == 12
        assert mikan._parse_cn_number("二十") == 20

    async def test_parse_entry_no_title_returns_none(self, mikan):
        entry = SimpleNamespace(title=None, link="https://mikanani.me/page")
        entry.get = lambda key, default=None: [] if key == "enclosures" else default
        session = MagicMock()
        result = await mikan.parse_entry(entry, session)
        assert result is None

    async def test_parse_entry_no_download_url_returns_none(self, mikan):
        entry = SimpleNamespace(title="Test", link="https://mikanani.me/page")
        entry.get = lambda key, default=None: [] if key == "enclosures" else default
        session = MagicMock()
        result = await mikan.parse_entry(entry, session)
        assert result is None

    async def test_parse_entry_non_web_link_returns_none(self, mikan):
        """Mikan requires a valid web page link for metadata fetching."""
        entry = SimpleNamespace(title="Test", link="magnet:?xt=urn:btih:abc")
        entry.get = lambda key, default=None: (
            [{"href": "magnet:?xt=urn:btih:abc", "type": "application/x-bittorrent"}]
            if key == "enclosures"
            else default
        )
        session = MagicMock()
        result = await mikan.parse_entry(entry, session)
        assert result is None
