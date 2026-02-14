"""TMDB tool handlers for LLM function calling."""

import json
from typing import Any, Dict, List

from openai import pydantic_function_tool
from pydantic import BaseModel

from openlist_ani.logger import logger

from .api.tmdb import TMDBClient


class TMDBSearchArgs(BaseModel):
    """Arguments for TMDB search tool."""

    query: str


class TMDBVerifyArgs(BaseModel):
    """Arguments for TMDB season/episode verification tool."""

    anime_name: str
    season: int
    episode: int


def get_tmdb_tools():
    """Get TMDB function tools for LLM.

    Returns:
        List of pydantic function tools for TMDB operations
    """
    return [
        pydantic_function_tool(
            TMDBSearchArgs,
            name="search_tmdb",
            description=(
                "Search TMDB for anime details when the title is ambiguous "
                "or to confirm season context."
            ),
        ),
        pydantic_function_tool(
            TMDBVerifyArgs,
            name="verify_tmdb_season_episode",
            description=(
                "Verify and correct season/episode information using TMDB data. "
                "Use this to check if a specific season/episode exists or to start strict validation."
            ),
        ),
    ]


async def handle_search_tmdb(
    tool_call: Any, messages: List[Dict[str, Any]], tmdb_client: TMDBClient
) -> None:
    """Handle TMDB search tool call from LLM.

    Args:
        tool_call: The tool call object from LLM
        messages: Message history list to append results
        tmdb_client: TMDB API client instance
    """
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    query = args.get("query")
    logger.debug(f"LLM requesting TMDB search for: {query}")

    search_results = await tmdb_client.search_tv_show(query)
    simplified_results = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "original_name": r.get("original_name"),
            "first_air_date": r.get("first_air_date"),
            "overview": (r.get("overview") or "")[:200],
        }
        for r in search_results[:3]
    ]

    messages.append(
        {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": "search_tmdb",
            "content": json.dumps(simplified_results, ensure_ascii=False),
        }
    )


async def handle_verify_tmdb(
    tool_call: Any, messages: List[Dict[str, Any]], tmdb_client: TMDBClient
) -> None:
    """Handle TMDB verification tool call from LLM.

    Args:
        tool_call: The tool call object from LLM
        messages: Message history list to append results
        tmdb_client: TMDB API client instance
    """
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError:
        args = {}

    anime_name = args.get("anime_name")
    season = args.get("season", 1)
    episode = args.get("episode", 1)

    logger.debug(f"Verifying TMDB for '{anime_name}' S{season} E{episode}")

    # 1. Search name
    search_results = await tmdb_client.search_tv_show(anime_name)
    if not search_results:
        messages.append(
            {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": "verify_tmdb_season_episode",
                "content": json.dumps({"error": "Anime name not found in TMDB."}),
            }
        )
        return

    # Best match
    best_match = search_results[0]
    tmdb_id = best_match.get("id")
    official_name = best_match.get("name")

    # 2. Get details
    details = await tmdb_client.get_tv_show_details(tmdb_id)
    if not details:
        messages.append(
            {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": "verify_tmdb_season_episode",
                "content": json.dumps({"error": "Could not fetch details."}),
            }
        )
        return

    seasons = details.get("seasons", [])
    # Sort
    sorted_seasons = sorted(seasons, key=lambda x: x.get("season_number", 0))

    # Log season info for debugging
    logger.debug(
        f"TMDB Seasons for {official_name}: "
        + ", ".join(
            [
                f"S{s.get('season_number')} ({s.get('episode_count')} eps)"
                for s in sorted_seasons
            ]
        )
    )

    target_season_info = next(
        (s for s in sorted_seasons if s.get("season_number") == season), None
    )

    result_data = {
        "tmdb_id": tmdb_id,
        "anime_name": official_name,
        "status": "checked",
        "original_query": {"season": season, "episode": episode},
    }

    # Case 1: Check if target exists
    if target_season_info:
        ep_count = target_season_info.get("episode_count", 0)
        logger.debug(
            f"Target Season {season} found. Episode count: {ep_count}. Requested: {episode}"
        )

        if episode <= ep_count:
            # Fits perfectly
            result_data["verified_season"] = season
            result_data["verified_episode"] = episode
            result_data["message"] = "Season and episode match TMDB data."
        else:
            # S2 E25, but S2 has 12 eps.
            # Check absolute numbering mapping.
            logger.debug(
                f"Episode {episode} exceeds Season {season} count {ep_count}. Mappping absolute..."
            )
            _try_map_absolute(episode, sorted_seasons, result_data)
    else:
        # Season doesn't exist. Check absolute numbering.
        logger.debug(
            f"Season {season} NOT found in TMDB. Trying absolute mapping for Episode {episode}..."
        )
        _try_map_absolute(episode, sorted_seasons, result_data)

    messages.append(
        {
            "tool_call_id": tool_call.id,
            "role": "tool",
            "name": "verify_tmdb_season_episode",
            "content": json.dumps(result_data, ensure_ascii=False),
        }
    )


def _try_map_absolute(
    episode_abs: int, sorted_seasons: List[Dict[str, Any]], result_data: Dict[str, Any]
) -> None:
    """Try to map absolute episode number to season and episode.

    Args:
        episode_abs: Absolute episode number
        sorted_seasons: List of season information sorted by season number
        result_data: Result dictionary to update with mapping results
    """
    # Try to find which season this absolute episode belongs to.
    # Sum up episodes of seasons > 0 (usually).

    # We iterate all seasons. If special (0) is included in absolute count?
    # Usually absolute count ignores specials.
    regular_seasons = [s for s in sorted_seasons if s.get("season_number", 0) > 0]

    current_acc = 0
    mapped = False

    logger.debug(
        f"Starting absolute mapping for Episode {episode_abs}. Regular seasons: {[s.get('season_number') for s in regular_seasons]}"
    )

    for s in regular_seasons:
        s_num = s.get("season_number")
        s_count = s.get("episode_count", 0)

        range_end = current_acc + s_count
        logger.debug(
            f"Checking Season {s_num}: range {current_acc + 1} to {range_end} (count {s_count})"
        )

        if current_acc < episode_abs <= range_end:
            result_data["verified_season"] = s_num
            result_data["verified_episode"] = episode_abs - current_acc
            result_data["message"] = (
                f"Mapped absolute episode {episode_abs} to Season {s_num} Episode {episode_abs - current_acc}"
            )
            mapped = True
            logger.debug(f"Mapping success: S{s_num}E{episode_abs - current_acc}")
            break

        current_acc += s_count

    if not mapped:
        logger.warning(
            f"Failed to map Episode {episode_abs} to any season. Total eps: {current_acc}"
        )
        result_data["message"] = (
            "Could not map to any season via absolute numbering. Data might be missing or episode is too high."
        )
