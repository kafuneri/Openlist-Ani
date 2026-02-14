"""
OpenList downloader implementation.

This module provides the OpenListDownloader class which implements
the BaseDownloader interface for downloading via OpenList's offline
download functionality.
"""

import asyncio
import os
import re
from typing import Optional

from openlist_ani.logger import logger

from ..model.task import DownloadState, DownloadTask
from .api.model import OfflineDownloadTool, OpenlistTaskState
from .api.openlist import OpenListClient
from .base import BaseDownloader, StateTransition


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are invalid in filenames."""
    # Invalid chars for Windows: < > : " / \ | ? *
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, " ", name)
    sanitized = sanitized.strip()
    return sanitized


def format_anime_episode(
    anime_name: Optional[str], season: Optional[int], episode: Optional[int]
) -> str:
    """Safely format anime episode info, handling None values."""
    name = anime_name or "Unknown"
    season_str = f"S{season:02d}" if season is not None else "S??"
    episode_str = f"E{episode:02d}" if episode is not None else "E??"
    return f"{name} {season_str}{episode_str}"


class OpenListDownloader(BaseDownloader):
    """
    Downloader implementation using OpenList's offline download API.

    This downloader:
    - Creates temp directories for downloads
    - Uses OpenList's offline download (aria2, qBittorrent, etc.)
    - Monitors download progress via task status
    - Renames and moves files to final location
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        offline_download_tool: OfflineDownloadTool | str,
        rename_format: str,
    ):
        if not base_url:
            raise ValueError("base_url is required")
        if offline_download_tool is None:
            raise ValueError("offline_download_tool is required")
        if rename_format is None:
            raise ValueError("rename_format is required")

        self._base_url = base_url
        self._token = token
        self._offline_download_tool = offline_download_tool
        self._rename_format = rename_format
        self._client: Optional[OpenListClient] = None

    @property
    def client(self) -> OpenListClient:
        """Lazy-initialize the OpenList client."""
        if self._client is None:
            self._client = OpenListClient(
                base_url=self._base_url,
                token=self._token,
            )
        return self._client

    @property
    def downloader_type(self) -> str:
        return "openlist"

    async def handle_pending(self, task: DownloadTask) -> StateTransition:
        """Handle PENDING state: create temp dir and start download."""
        logger.debug(f"Preparing: {task.resource_info.title}")

        # Create temporary directory
        temp_dir_name = task.id
        temp_path = f"{task.save_path.rstrip('/')}/{temp_dir_name}"

        logger.debug(f"Creating temporary directory: {temp_path}")
        if not await self.client.mkdir(temp_path):
            return StateTransition(
                success=False,
                error_message=f"Failed to create temporary directory: {temp_path}",
            )

        # Get initial files for later detection
        files = await self.client.list_files(temp_path)
        task.initial_files = [f.name for f in files] if files else []
        task.temp_path = temp_path

        # Start offline download
        logger.info(
            f"Starting download: {format_anime_episode(task.resource_info.anime_name, task.resource_info.season, task.resource_info.episode)}"
        )
        logger.debug(f"  Title: {task.resource_info.title}")
        logger.debug(f"  URL: {task.resource_info.download_url}")
        logger.debug(f"  Temp path: {temp_path}")

        tasks = await self.client.add_offline_download(
            urls=[task.resource_info.download_url],
            path=temp_path,
            tool=self._offline_download_tool,
        )

        if not tasks:
            await self._cleanup(task)
            return StateTransition(
                success=False,
                error_message="Failed to create offline download task",
            )

        task.extra_data["task_id"] = tasks[0].id
        logger.debug(f"Download task created with ID: {tasks[0].id}")

        return StateTransition(
            success=True,
            next_state=DownloadState.DOWNLOADING,
            should_continue=True,
        )

    async def handle_downloading(self, task: DownloadTask) -> StateTransition:
        """Handle DOWNLOADING state: monitor progress."""
        task_id = task.extra_data.get("task_id")
        if not task_id:
            return StateTransition(
                success=False,
                error_message="No task ID available",
            )

        # Check undone tasks
        undone_tasks = await self.client.get_offline_download_undone()
        if undone_tasks is None:
            # API error - retry after delay
            return StateTransition(
                success=True,
                should_continue=True,
                delay_seconds=5.0,
            )

        # Look for task in undone
        for api_task in undone_tasks:
            if api_task.id == task_id:
                progress = float(api_task.progress) if api_task.progress else None
                if progress is not None:
                    # Log progress at info level for key milestones
                    if progress > 0 and int(progress) % 25 == 0:
                        logger.info(
                            f"Downloading [{format_anime_episode(task.resource_info.anime_name, task.resource_info.season, task.resource_info.episode)}]: {progress:.0f}%"
                        )
                    else:
                        logger.debug(f"Progress: {progress:.1f}%")
                # Still downloading - check again later
                return StateTransition(
                    success=True,
                    should_continue=True,
                    delay_seconds=5.0,
                )

        # Not in undone - check done tasks
        done_tasks = await self.client.get_offline_download_done()
        if done_tasks is None:
            # API error - retry after delay
            return StateTransition(
                success=True,
                should_continue=True,
                delay_seconds=5.0,
            )

        for api_task in done_tasks:
            if api_task.id == task_id:
                if api_task.state == OpenlistTaskState.Succeeded:
                    # Download completed - detect file
                    logger.debug(
                        f"Download finished, detecting file for: {task.resource_info.title}"
                    )
                    downloaded_filename = await self._detect_downloaded_file(task)
                    if not downloaded_filename:
                        await self._cleanup(task)
                        return StateTransition(
                            success=False,
                            error_message="Download completed but no file found",
                        )
                    task.downloaded_filename = downloaded_filename
                    return StateTransition(
                        success=True,
                        next_state=DownloadState.DOWNLOADED,
                        should_continue=True,
                    )
                else:
                    logger.error(f"Download failed with state: {api_task.state}")
                    await self._cleanup(task)
                    return StateTransition(
                        success=False,
                        error_message=f"Task failed with state: {api_task.state}",
                    )

        # Task not found - may have been deleted
        await self._cleanup(task)
        return StateTransition(
            success=False,
            error_message=f"Task {task_id} not found",
        )

    async def _detect_downloaded_file(self, task: DownloadTask) -> Optional[str]:
        """Detect the downloaded file in the temp directory."""
        if not task.temp_path:
            return None

        files = await self.client.list_files(task.temp_path)
        if not files:
            return None

        initial_files = set(task.initial_files)

        for file_info in files:
            name = file_info.name
            # Skip incomplete download markers
            if name.endswith(".aria2") or name.endswith(".downloading"):
                continue
            # Check if it's a new file
            if name not in initial_files:
                return name

        return None

    async def handle_downloaded(self, task: DownloadTask) -> StateTransition:
        """Handle DOWNLOADED state: rename and move file."""
        logger.debug(f"Post-processing: {task.resource_info.title}")

        if not task.downloaded_filename:
            await self._cleanup(task)
            return StateTransition(
                success=False,
                error_message="No downloaded filename available",
            )

        if not task.temp_path:
            await self._cleanup(task)
            return StateTransition(
                success=False,
                error_message="No temp_path available",
            )

        # Build final path
        anime_name = sanitize_filename(task.resource_info.anime_name or "Unknown")
        season = task.resource_info.season or 1
        episode = task.resource_info.episode or 1
        season_dir = f"Season {season}"
        final_dir_path = f"{task.save_path.rstrip('/')}/{anime_name}/{season_dir}"

        # Get extension from downloaded file
        _, ext = os.path.splitext(task.downloaded_filename)
        if ext == "":
            ext = ".mp4"  # Default to .mp4 if no extension

        # Build final filename using config format
        rename_context = vars(task.resource_info).copy()
        rename_context["anime_name"] = anime_name
        if "title" in rename_context:
            del rename_context["title"]
        version = rename_context.pop("version", 1) or 1

        try:
            final_filename_stem = self._rename_format.format(**rename_context).strip()
        except Exception as e:
            logger.warning(
                f"Failed to format filename using format string: '{self._rename_format}'. "
                f"Error: {e}. Falling back to default."
            )
            final_filename_stem = f"{anime_name} S{season:02d}E{episode:02d}"

        # Append version suffix when version > 1
        if version > 1:
            final_filename_stem = f"{final_filename_stem} v{version}"

        final_filename = f"{final_filename_stem}{ext}".strip()

        # Create final directory
        if not await self.client.mkdir(final_dir_path):
            await self._cleanup(task)
            return StateTransition(
                success=False,
                error_message=f"Failed to create directory: {final_dir_path}",
            )

        # Rename file in temp directory if needed
        file_to_move = task.downloaded_filename
        if final_filename != task.downloaded_filename:
            logger.debug(f"Renaming file to: {final_filename}")
            temp_file_path = f"{task.temp_path}/{task.downloaded_filename}"
            if await self.client.rename_file(temp_file_path, final_filename):
                file_to_move = final_filename
                logger.debug("Waiting for remote server cache to refresh...")
                await asyncio.sleep(5)
                logger.debug(f"Renamed {task.downloaded_filename} to {final_filename}")
            else:
                logger.warning(
                    f"Rename failed, will move with original name: {task.downloaded_filename}"
                )

        # Move file to final destination
        logger.debug(
            f"Moving file to final destination: {final_dir_path}/{file_to_move}"
        )
        if not await self.client.move_file(
            task.temp_path, final_dir_path, [file_to_move]
        ):
            await self._cleanup(task)
            return StateTransition(
                success=False,
                error_message=f"Failed to move file to: {final_dir_path}",
            )

        task.final_path = f"{final_dir_path}/{file_to_move}"
        return StateTransition(
            success=True,
            next_state=DownloadState.POST_PROCESSING,
            should_continue=True,
        )

    async def handle_post_processing(self, task: DownloadTask) -> StateTransition:
        """Handle POST_PROCESSING state: cleanup temp directory and complete."""
        await self._cleanup(task)
        logger.info(
            f"Download completed: {format_anime_episode(task.resource_info.anime_name, task.resource_info.season, task.resource_info.episode)}"
        )
        return StateTransition(
            success=True,
            next_state=DownloadState.COMPLETED,
            should_continue=False,
        )

    async def _cleanup(self, task: DownloadTask) -> bool:
        """Clean up temporary directory."""
        if not task.temp_path:
            return True

        temp_dir_name = task.id
        logger.debug(f"Cleaning up temporary directory: {temp_dir_name}")

        return await self.client.remove_path(task.save_path, [temp_dir_name])
