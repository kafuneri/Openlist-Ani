"""Tests for OpenListClient.check_health method."""

from unittest.mock import AsyncMock, patch

import pytest

from openlist_ani.core.download.downloader.api.openlist import OpenListClient


@pytest.fixture
def client():
    """Create a basic OpenListClient for testing."""
    return OpenListClient(
        base_url="http://localhost:5244",
        token="test-token",
        max_retries=1,
    )


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------


class TestCheckHealth:
    @pytest.mark.asyncio
    async def test_health_success(self, client):
        """Should return True when server responds with code 200."""
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"code": 200, "data": {}},
        ):
            result = await client.check_health()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_failure_non_200(self, client):
        """Should return False when server responds with non-200 code."""
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value={"code": 500, "message": "Server error"},
        ):
            result = await client.check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_failure_none(self, client):
        """Should return False when request returns None (network error)."""
        with patch.object(
            client,
            "_get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await client.check_health()
            assert result is False

    @pytest.mark.asyncio
    async def test_health_calls_correct_url(self, client):
        """Should call the public settings endpoint."""
        mock_get = AsyncMock(return_value={"code": 200, "data": {}})
        with patch.object(client, "_get", mock_get):
            await client.check_health()
            mock_get.assert_called_once_with(
                "http://localhost:5244/api/public/settings"
            )
