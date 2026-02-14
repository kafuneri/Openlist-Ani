"""Tests for openlist_ani.core.parser.tool.tmdb_tool module."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from openlist_ani.core.parser.tool.tmdb_tool import (
    TMDBSearchArgs,
    TMDBVerifyArgs,
    _try_map_absolute,
    get_tmdb_tools,
    handle_search_tmdb,
    handle_verify_tmdb,
)

# =========================================================================
# get_tmdb_tools
# =========================================================================


class TestGetTmdbTools:
    def test_returns_two_tools(self):
        tools = get_tmdb_tools()
        assert len(tools) == 2

    def test_tool_names(self):
        tools = get_tmdb_tools()
        names = {t["function"]["name"] for t in tools}
        assert names == {"search_tmdb", "verify_tmdb_season_episode"}

    def test_tools_have_function_key(self):
        tools = get_tmdb_tools()
        for t in tools:
            assert "function" in t
            assert "name" in t["function"]
            assert "parameters" in t["function"]


# =========================================================================
# _try_map_absolute — pure function, thoroughly testable
# =========================================================================


def _make_season(num: int, eps: int) -> dict:
    return {"season_number": num, "episode_count": eps}


class TestTryMapAbsolute:
    """Test absolute episode → season/episode mapping logic."""

    def test_single_season_episode_in_range(self):
        seasons = [_make_season(1, 12)]
        result = {}
        _try_map_absolute(5, seasons, result)
        assert result["verified_season"] == 1
        assert result["verified_episode"] == 5

    def test_single_season_last_episode(self):
        seasons = [_make_season(1, 12)]
        result = {}
        _try_map_absolute(12, seasons, result)
        assert result["verified_season"] == 1
        assert result["verified_episode"] == 12

    def test_single_season_first_episode(self):
        seasons = [_make_season(1, 12)]
        result = {}
        _try_map_absolute(1, seasons, result)
        assert result["verified_season"] == 1
        assert result["verified_episode"] == 1

    def test_maps_to_second_season(self):
        seasons = [_make_season(1, 12), _make_season(2, 12)]
        result = {}
        _try_map_absolute(15, seasons, result)
        assert result["verified_season"] == 2
        assert result["verified_episode"] == 3

    def test_maps_to_third_season(self):
        seasons = [_make_season(1, 12), _make_season(2, 13), _make_season(3, 12)]
        result = {}
        _try_map_absolute(26, seasons, result)
        assert result["verified_season"] == 3
        assert result["verified_episode"] == 1

    def test_exact_boundary_end_of_first_season(self):
        seasons = [_make_season(1, 12), _make_season(2, 12)]
        result = {}
        _try_map_absolute(12, seasons, result)
        assert result["verified_season"] == 1
        assert result["verified_episode"] == 12

    def test_exact_boundary_start_of_second_season(self):
        seasons = [_make_season(1, 12), _make_season(2, 12)]
        result = {}
        _try_map_absolute(13, seasons, result)
        assert result["verified_season"] == 2
        assert result["verified_episode"] == 1

    def test_episode_exceeds_all_seasons(self):
        seasons = [_make_season(1, 12), _make_season(2, 12)]
        result = {}
        _try_map_absolute(100, seasons, result)
        assert "verified_season" not in result
        assert "Could not map" in result.get("message", "")

    def test_episode_zero_no_match(self):
        """Episode 0 should not match any season (range is 1-based)."""
        seasons = [_make_season(1, 12)]
        result = {}
        _try_map_absolute(0, seasons, result)
        assert "verified_season" not in result

    def test_negative_episode_no_match(self):
        seasons = [_make_season(1, 12)]
        result = {}
        _try_map_absolute(-1, seasons, result)
        assert "verified_season" not in result

    def test_ignores_special_season_zero(self):
        """Season 0 (specials) should be excluded from absolute mapping."""
        seasons = [_make_season(0, 5), _make_season(1, 12)]
        result = {}
        _try_map_absolute(3, seasons, result)
        assert result["verified_season"] == 1
        assert result["verified_episode"] == 3

    def test_empty_seasons_list(self):
        result = {}
        _try_map_absolute(1, [], result)
        assert "verified_season" not in result
        assert "Could not map" in result.get("message", "")

    def test_season_with_zero_episodes(self):
        seasons = [_make_season(1, 0), _make_season(2, 12)]
        result = {}
        _try_map_absolute(5, seasons, result)
        assert result["verified_season"] == 2
        assert result["verified_episode"] == 5

    def test_preserves_existing_result_data(self):
        """_try_map_absolute should add to result_data, not overwrite existing keys."""
        seasons = [_make_season(1, 12)]
        result = {"tmdb_id": 999, "anime_name": "Test"}
        _try_map_absolute(5, seasons, result)
        assert result["tmdb_id"] == 999
        assert result["anime_name"] == "Test"
        assert result["verified_season"] == 1
        assert result["verified_episode"] == 5


# =========================================================================
# Pydantic args models
# =========================================================================


class TestToolArgModels:
    def test_tmdb_search_args(self):
        args = TMDBSearchArgs(query="frieren")
        assert args.query == "frieren"

    def test_tmdb_verify_args(self):
        args = TMDBVerifyArgs(anime_name="Frieren", season=1, episode=5)
        assert args.anime_name == "Frieren"
        assert args.season == 1
        assert args.episode == 5


# =========================================================================
# handle_search_tmdb — async, needs mock
# =========================================================================


def _make_tool_call(name: str, arguments: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id="call_001",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


class TestHandleSearchTmdb:
    @pytest.mark.asyncio
    async def test_appends_search_results_to_messages(self):
        tool_call = _make_tool_call("search_tmdb", {"query": "frieren"})
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [
            {
                "id": 209867,
                "name": "葬送のフリーレン",
                "original_name": "Sousou no Frieren",
                "first_air_date": "2023-09-29",
                "overview": "An elf mage...",
            }
        ]

        await handle_search_tmdb(tool_call, messages, mock_client)

        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_001"
        assert msg["name"] == "search_tmdb"
        content = json.loads(msg["content"])
        assert len(content) == 1
        assert content[0]["id"] == 209867

    @pytest.mark.asyncio
    async def test_empty_search_results(self):
        tool_call = _make_tool_call("search_tmdb", {"query": "nonexistent"})
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = []

        await handle_search_tmdb(tool_call, messages, mock_client)

        assert len(messages) == 1
        content = json.loads(messages[0]["content"])
        assert content == []

    @pytest.mark.asyncio
    async def test_limits_to_three_results(self):
        tool_call = _make_tool_call("search_tmdb", {"query": "test"})
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [
            {
                "id": i,
                "name": f"Show {i}",
                "original_name": "",
                "first_air_date": "",
                "overview": "",
            }
            for i in range(10)
        ]

        await handle_search_tmdb(tool_call, messages, mock_client)

        content = json.loads(messages[0]["content"])
        assert len(content) == 3

    @pytest.mark.asyncio
    async def test_truncates_overview(self):
        tool_call = _make_tool_call("search_tmdb", {"query": "test"})
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [
            {
                "id": 1,
                "name": "Test",
                "original_name": "",
                "first_air_date": "",
                "overview": "x" * 500,
            }
        ]

        await handle_search_tmdb(tool_call, messages, mock_client)

        content = json.loads(messages[0]["content"])
        assert len(content[0]["overview"]) <= 200

    @pytest.mark.asyncio
    async def test_invalid_json_arguments_does_not_crash(self):
        """Malformed arguments should not cause a crash."""
        tool_call = SimpleNamespace(
            id="call_bad",
            function=SimpleNamespace(name="search_tmdb", arguments="not valid json"),
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = []

        await handle_search_tmdb(tool_call, messages, mock_client)

        # Should still append a message (with query=None)
        assert len(messages) == 1


# =========================================================================
# handle_verify_tmdb — async, needs mock
# =========================================================================


class TestHandleVerifyTmdb:
    @pytest.mark.asyncio
    async def test_verify_exact_match(self):
        tool_call = _make_tool_call(
            "verify_tmdb_season_episode",
            {"anime_name": "Frieren", "season": 1, "episode": 5},
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [
            {"id": 209867, "name": "葬送のフリーレン"}
        ]
        mock_client.get_tv_show_details.return_value = {
            "seasons": [
                {"season_number": 0, "episode_count": 2},
                {"season_number": 1, "episode_count": 28},
            ]
        }

        await handle_verify_tmdb(tool_call, messages, mock_client)

        assert len(messages) == 1
        content = json.loads(messages[0]["content"])
        assert content["verified_season"] == 1
        assert content["verified_episode"] == 5
        assert content["tmdb_id"] == 209867
        assert content["anime_name"] == "葬送のフリーレン"

    @pytest.mark.asyncio
    async def test_verify_triggers_absolute_mapping(self):
        """Episode exceeds season count → should try absolute mapping."""
        tool_call = _make_tool_call(
            "verify_tmdb_season_episode",
            {"anime_name": "Test", "season": 1, "episode": 20},
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [{"id": 100, "name": "Test"}]
        mock_client.get_tv_show_details.return_value = {
            "seasons": [
                {"season_number": 1, "episode_count": 12},
                {"season_number": 2, "episode_count": 12},
            ]
        }

        await handle_verify_tmdb(tool_call, messages, mock_client)

        content = json.loads(messages[0]["content"])
        assert content["verified_season"] == 2
        assert content["verified_episode"] == 8

    @pytest.mark.asyncio
    async def test_verify_not_found_in_tmdb(self):
        tool_call = _make_tool_call(
            "verify_tmdb_season_episode",
            {"anime_name": "NonExistent", "season": 1, "episode": 1},
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = []

        await handle_verify_tmdb(tool_call, messages, mock_client)

        content = json.loads(messages[0]["content"])
        assert "error" in content

    @pytest.mark.asyncio
    async def test_verify_no_details_available(self):
        tool_call = _make_tool_call(
            "verify_tmdb_season_episode",
            {"anime_name": "Test", "season": 1, "episode": 1},
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [{"id": 100, "name": "Test"}]
        mock_client.get_tv_show_details.return_value = {}

        await handle_verify_tmdb(tool_call, messages, mock_client)

        content = json.loads(messages[0]["content"])
        assert "error" in content

    @pytest.mark.asyncio
    async def test_verify_season_not_found_triggers_absolute(self):
        """Requested season doesn't exist → absolute mapping."""
        tool_call = _make_tool_call(
            "verify_tmdb_season_episode",
            {"anime_name": "Test", "season": 5, "episode": 3},
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = [{"id": 100, "name": "Test"}]
        mock_client.get_tv_show_details.return_value = {
            "seasons": [
                {"season_number": 1, "episode_count": 12},
                {"season_number": 2, "episode_count": 12},
            ]
        }

        await handle_verify_tmdb(tool_call, messages, mock_client)

        content = json.loads(messages[0]["content"])
        # Episode 3 with absolute mapping → S1E3
        assert content["verified_season"] == 1
        assert content["verified_episode"] == 3

    @pytest.mark.asyncio
    async def test_verify_invalid_json_arguments_does_not_crash(self):
        """Malformed arguments should not cause a crash."""
        tool_call = SimpleNamespace(
            id="call_bad",
            function=SimpleNamespace(
                name="verify_tmdb_season_episode", arguments="{{invalid"
            ),
        )
        messages: list = []
        mock_client = AsyncMock()
        mock_client.search_tv_show.return_value = []

        await handle_verify_tmdb(tool_call, messages, mock_client)

        assert len(messages) == 1
