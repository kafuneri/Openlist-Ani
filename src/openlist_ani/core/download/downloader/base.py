from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..model.task import DownloadState, DownloadTask


@dataclass
class StateTransition:
    """Result of state handler execution."""

    success: bool
    next_state: Optional[DownloadState] = None
    should_continue: bool = True  # Continue to next state immediately
    delay_seconds: float = 0  # Delay before continuing (for polling)
    error_message: Optional[str] = None


class BaseDownloader(ABC):
    """Abstract base class for downloader implementations."""

    @property
    @abstractmethod
    def downloader_type(self) -> str:
        """Return the unique identifier for this downloader type."""
        pass

    @abstractmethod
    async def handle_pending(self, task: DownloadTask) -> StateTransition:
        """Handle PENDING state: prepare and start download."""
        pass

    @abstractmethod
    async def handle_downloading(self, task: DownloadTask) -> StateTransition:
        """Handle DOWNLOADING state: monitor progress."""
        pass

    @abstractmethod
    async def handle_downloaded(self, task: DownloadTask) -> StateTransition:
        """Handle DOWNLOADED state: post-process."""
        pass

    @abstractmethod
    async def handle_post_processing(self, task: DownloadTask) -> StateTransition:
        """Handle POST_PROCESSING state: cleanup and complete."""
        pass
