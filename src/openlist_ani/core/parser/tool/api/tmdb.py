import asyncio
from typing import Any, Dict, List

import aiohttp

from openlist_ani.config import config
from openlist_ani.logger import logger


class TMDBClient:
    def __init__(self):
        self.base_url = "https://api.tmdb.org/3"

    @property
    def api_key(self) -> str:
        return config.llm.tmdb_api_key

    async def search_tv_show(self, query: str) -> List[Dict[str, Any]]:
        """Search for a TV show on TMDB.

        Args:
            query: Search query string

        Returns:
            List of search results
        """
        if not self.api_key:
            logger.warning("TMDB API key not set, skipping search.")
            return []

        url = f"{self.base_url}/search/tv"
        params = {
            "api_key": self.api_key,
            "query": query,
            "language": config.llm.tmdb_language,
            "include_adult": "true",
        }

        timeout = aiohttp.ClientTimeout(total=30, connect=30, sock_read=30)

        try:
            async with aiohttp.ClientSession(
                timeout=timeout, trust_env=True
            ) as session:
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data.get("results", [])
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"TMDB search request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in TMDB search: {e}")
            return []

    async def get_tv_show_details(self, tmdb_id: int) -> Dict[str, Any]:
        """Get detailed information for a TV show including seasons.

        Args:
            tmdb_id: TMDB TV show ID

        Returns:
            TV show details dictionary
        """
        if not self.api_key:
            logger.warning("TMDB API key not set")
            return {}

        url = f"{self.base_url}/tv/{tmdb_id}"
        params = {
            "api_key": self.api_key,
            "language": config.llm.tmdb_language,
        }

        timeout = aiohttp.ClientTimeout(total=30, connect=30, sock_read=30)

        try:
            async with aiohttp.ClientSession(
                timeout=timeout, trust_env=True
            ) as session:
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.warning(f"TMDB details request failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error getting TMDB details: {e}")
            return {}
