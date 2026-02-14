import asyncio
from typing import TYPE_CHECKING, List, Optional

from ..config import config
from ..database import db
from ..logger import logger
from .website import AnimeResourceInfo, WebsiteBase, WebsiteFactory

if TYPE_CHECKING:
    from .download.manager import DownloadManager


class RSSManager:
    """Manager for RSS feed subscriptions.

    Handles fetching and parsing RSS feeds from multiple sources,
    checking for duplicates, and filtering already-downloaded content.
    """

    def __init__(self, download_manager: "DownloadManager"):
        """Initialize RSS Manager.

        Args:
            download_manager: DownloadManager for checking active tasks
        """
        self._download_manager = download_manager
        self._factory = WebsiteFactory()

    def _get_website_handler(self, url: str) -> Optional[WebsiteBase]:
        """Get appropriate handler using WebsiteFactory."""
        try:
            return self._factory.create(url)
        except Exception as e:
            logger.warning(f"Failed to create handler for URL {url}: {e}")
            return None

    async def check_update(self) -> List[AnimeResourceInfo]:
        """Check all RSS subscriptions for updates.

        Returns:
            List of new anime resources that are not downloaded
            and not currently being processed.
        """
        urls = config.rss.urls
        if not urls:
            return []

        tasks = [
            handler.fetch_feed(url)
            for url in urls
            if (handler := self._get_website_handler(url))
        ]

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        new_entries: List[AnimeResourceInfo] = []

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Error fetching RSS: {res}")
                continue

            if not isinstance(res, list):
                logger.error(f"Unexpected RSS fetch result: {res}")
                continue

            for entry in res:
                if not entry.download_url:
                    continue

                # Check if already downloaded in database
                if await db.is_downloaded(entry.title):
                    logger.debug(f"Skipping already downloaded: {entry.title}")
                    continue

                # Check if currently being processed by download manager
                if self._download_manager and self._download_manager.is_downloading(
                    entry
                ):
                    logger.debug(f"Skipping already queued: {entry.title}")
                    continue

                new_entries.append(entry)

        if new_entries:
            logger.info(f"RSS check: {len(new_entries)} new entries found")
        else:
            logger.debug("RSS check: no new entries")

        return new_entries
