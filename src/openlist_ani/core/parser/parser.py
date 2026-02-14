import asyncio
import json
from typing import Optional

from openai import AsyncOpenAI

from ...config import config
from ...logger import logger
from ..website.model import AnimeResourceInfo
from .model import ResourceTitleParseResult
from .tool.api.tmdb import TMDBClient
from .tool.tmdb_tool import get_tmdb_tools, handle_search_tmdb, handle_verify_tmdb
from .utils import parse_json_from_markdown


async def parse_metadata(
    entry: AnimeResourceInfo,
) -> Optional[ResourceTitleParseResult]:
    """
    Parse metadata from AnimeResourceInfo using OpenAI LLM and TMDB.

    Args:
        entry: Anime resource information with title to parse

    Returns:
        Parsed metadata or None if extraction fails
    """
    if not config.llm.openai_api_key:
        logger.warning("OpenAI API key not set, skipping LLM extraction.")
        return None

    client = AsyncOpenAI(
        api_key=config.llm.openai_api_key,
        base_url=config.llm.openai_base_url,
        timeout=30.0,
    )
    model = config.llm.openai_model
    tmdb_client = TMDBClient()

    tools = []
    tools.extend(get_tmdb_tools())

    system_prompt = """You are an intelligent anime metadata parser.
Your task is to parse information from the RSS feed entry title.
Output the result in a valid JSON object matching the following structure:
{
    "anime_name": "string",
    "season": int,  // 0 for specials, 1 for Season 1. If the episode is a special episode(like 11.5), set season to 0.
    "episode": int,
    "quality": "string", // Enum: 2160p, 1080p, 720p, 480p, unknown
    "fansub": "string or null",
    "languages": ["string"], // Enum: 简, 繁, 日, 英, 未知
    "version": int, // Subtitle version, default to 1, if v2 or .v2 set to 2.
    "tmdb_id": int // Optional, if found via tools
}

CRITICAL RULES:
1. Parse the title first to extract initial information.
2. YOU MUST ALWAYS call 'search_tmdb' with the anime name to find the correct TMDB entry. This is MANDATORY.
3. After getting TMDB search results, select the best match and call 'verify_tmdb_season_episode' with the anime_name, season, and episode.
4. CRITICAL: Once 'verify_tmdb_season_episode' returns results:
   - If it returns 'anime_name', you MUST use it as the final anime_name. This is the official TMDB name.
   - If it returns 'verified_season' and 'verified_episode', you MUST use EXACTLY these values.
   - DO NOT override TMDB data with your own logic. TMDB is the source of truth.
5. TMDB DATA IS THE AUTHORITY: Even if the title says "Season 3" but TMDB structure maps it to "Season 1", you MUST output "Season 1". Accept TMDB's structure.
6. Using TMDB's official anime_name ensures consistency across all episodes.
7. Do not keep searching if TMDB mapping is clear - accept the verified results.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Feed Title: {entry.title}"},
    ]

    try:
        # Loop for tool calls
        for _ in range(5):
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            message = response.choices[0].message

            if not message.tool_calls:
                messages.append(message)
                break

            messages.append(message)
            for tool_call in message.tool_calls:
                if tool_call.function.name == "search_tmdb":
                    await handle_search_tmdb(tool_call, messages, tmdb_client)
                elif tool_call.function.name == "verify_tmdb_season_episode":
                    await handle_verify_tmdb(tool_call, messages, tmdb_client)

        # Should have final answer now
        last_msg = messages[-1]

        # If the last message is a dict, get final response from LLM
        if isinstance(last_msg, dict):
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
            )
            last_msg = response.choices[0].message
            messages.append(last_msg)

        elif hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            pass

        content = last_msg.content or ""
        json_str = parse_json_from_markdown(content)

        if not json_str:
            logger.error(f"LLM failed to return valid JSON. Output: {content}")
            return None

        try:
            parse_result = ResourceTitleParseResult.model_validate_json(json_str)
        except Exception as e:
            logger.error(f"JSON validation failed: {e}. JSON: {json_str}")
            return None

        return parse_result

    except asyncio.TimeoutError:
        logger.error(f"LLM request timeout for: {entry.title}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in LLM response: {e}")
        return None
    except Exception as e:
        logger.error(f"Error during LLM parsing: {e}")
        return None
