"""
Search anime resources tool.
"""

from typing import Any, Dict, List
from urllib.parse import quote_plus

from ...core.website import WebsiteFactory
from ...database import db
from ...logger import logger
from ..model import SearchResult
from .base import BaseTool


class SearchAnimeTool(BaseTool):
    """Tool for searching anime resources on websites."""

    @property
    def name(self) -> str:
        return "search_anime_resources"

    @property
    def description(self) -> str:
        return "Search for anime resources on specified website. Returns list of resources with download URLs and metadata."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "anime_name": {
                    "type": "string",
                    "description": "The anime name to search for",
                },
                "website": {
                    "type": "string",
                    "description": "Website to search on. Options: mikan (蜜柑计划), dmhy (动漫花园), acgrip (ACG.RIP)",
                    "enum": ["mikan", "dmhy", "acgrip"],
                },
            },
            "required": ["anime_name", "website"],
        }

    async def execute(self, anime_name: str, website: str, **kwargs) -> str:
        """Search anime resources on specified website.

        Args:
            anime_name: Anime name to search
            website: Website to search on

        Returns:
            Formatted search results
        """
        logger.info(f"Assistant: Searching {anime_name} on {website}")

        results: List[SearchResult] = []

        try:
            # Build search RSS URL based on website
            encoded_name = quote_plus(anime_name)
            if website == "mikan":
                search_url = f"https://mikanani.me/RSS/Search?searchstr={encoded_name}"
            elif website == "dmhy":
                search_url = (
                    f"https://dmhy.org/topics/rss/rss.xml?keyword={encoded_name}"
                )
            elif website == "acgrip":
                search_url = f"https://acg.rip/.xml?term={encoded_name}"
            else:
                logger.error(f"Assistant: Unsupported website {website}")
                return f"❌ Unsupported website: {website}"

            # Fetch and parse RSS
            factory = WebsiteFactory()
            handler = factory.create(search_url)
            if not handler:
                logger.error(f"Assistant: Failed to create handler for {search_url}")
                return f"❌ Failed to create handler for {website}"

            entries = await handler.fetch_feed(search_url)
            logger.info(f"Assistant: Found {len(entries)} results for {anime_name}")

            # Check each entry against database
            for entry in entries:
                is_downloaded = await db.is_downloaded(entry.title)
                results.append(
                    SearchResult(
                        title=entry.title,
                        download_url=entry.download_url or "",
                        is_downloaded=is_downloaded,
                        anime_name=entry.anime_name,
                        episode=entry.episode,
                        quality=entry.quality.value if entry.quality else None,
                    )
                )

        except Exception:
            logger.exception(f"Assistant: Error searching {anime_name} on {website}")
            return f"❌ Error searching {anime_name} on {website}"

        if not results:
            return f"❌ No resources found for {anime_name} on {website}"

        # Separate downloaded and new resources
        downloaded = [r for r in results if r.is_downloaded]
        new_resources = [r for r in results if not r.is_downloaded]

        msg = f"🔍 Search Results for '{anime_name}' on {website}:\n\n"

        if downloaded:
            msg += f"📦 Already Downloaded ({len(downloaded)} resources):\n"
            for idx, res in enumerate(downloaded[:10], 1):
                msg += f"  {idx}. {res.title}\n"
                if res.quality:
                    msg += f"     Quality: {res.quality}\n"
            if len(downloaded) > 10:
                msg += f"  ...and {len(downloaded) - 10} more\n"
            msg += "\n⚠️ These resources are already downloaded, do NOT download them again!\n\n"

        if new_resources:
            msg += f"🆕 New Resources ({len(new_resources)} available):\n"
            for idx, res in enumerate(new_resources[:10], 1):
                msg += f"  {idx}. {res.title}\n"
                if res.quality:
                    msg += f"     Quality: {res.quality}\n"
                msg += f"     Download URL: {res.download_url}\n\n"
            if len(new_resources) > 10:
                msg += f"  ...and {len(new_resources) - 10} more\n"
        else:
            msg += "ℹ️ No new resources found (all have been downloaded)\n"

        return msg
