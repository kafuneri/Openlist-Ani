"""Tests for AniapiWebsite entry parsing."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openlist_ani.core.website.aniapi import AniapiWebsite


@pytest.fixture
def aniapi():
    return AniapiWebsite()


class TestAniapiWebsite:
    async def test_parse_entry_normal(self, aniapi):
        entry = SimpleNamespace(
            title="[ANi] 迷宫饭 - 05 [1080p][WEB-DL][CHS]",
            link="https://resources.ani.rip/file.mp4",
        )
        entry.get = lambda key, default=None: [] if key == "enclosures" else default
        session = MagicMock()
        result = await aniapi.parse_entry(entry, session)
        assert result is not None
        assert result.title == "[ANi] 迷宫饭 - 05 [1080p][WEB-DL][CHS]"
        assert result.fansub == "ANi"
        assert result.download_url == "https://resources.ani.rip/file.mp4"

    async def test_parse_entry_no_title(self, aniapi):
        entry = SimpleNamespace(title=None, link="https://example.com/file.mp4")
        entry.get = lambda key, default=None: [] if key == "enclosures" else default
        session = MagicMock()
        result = await aniapi.parse_entry(entry, session)
        assert result is None

    async def test_parse_entry_no_link(self, aniapi):
        entry = SimpleNamespace(title="[ANi] Test - 01")
        entry.link = ""
        entry.get = lambda key, default=None: [] if key == "enclosures" else default
        session = MagicMock()
        result = await aniapi.parse_entry(entry, session)
        assert result is None

    async def test_enclosure_fallback(self, aniapi):
        """When link is empty, should fall back to enclosure href."""
        entry = SimpleNamespace(title="[ANi] Test - 01", link="")
        entry.get = lambda key, default=None: (
            [{"href": "https://cdn.example.com/video.mp4"}]
            if key == "enclosures"
            else default
        )
        session = MagicMock()
        result = await aniapi.parse_entry(entry, session)
        assert result is not None
        assert result.download_url == "https://cdn.example.com/video.mp4"
