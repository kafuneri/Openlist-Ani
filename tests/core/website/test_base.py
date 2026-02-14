"""Tests for WebsiteBase.fetch_feed robustness against network errors."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import aiohttp

from openlist_ani.core.website.common import CommonRSSWebsite


class TestWebsiteBaseFetchFeed:
    """Test that fetch_feed handles network errors gracefully."""

    async def test_fetch_feed_timeout_returns_empty(self):
        """Timeout during HTTP request must return [], not raise."""
        parser = CommonRSSWebsite()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.side_effect = asyncio.TimeoutError()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_ctx

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session

        with patch("aiohttp.ClientSession", return_value=mock_cm):
            result = await parser.fetch_feed("https://example.com/rss")

        assert result == []

    async def test_fetch_feed_http_error_returns_empty(self):
        """HTTP errors must return [], not crash."""
        parser = CommonRSSWebsite()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.side_effect = aiohttp.ClientError("Connection refused")

        mock_session = MagicMock()
        mock_session.get.return_value = mock_ctx

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_session

        with patch("aiohttp.ClientSession", return_value=mock_cm):
            result = await parser.fetch_feed("https://example.com/rss")

        assert result == []
