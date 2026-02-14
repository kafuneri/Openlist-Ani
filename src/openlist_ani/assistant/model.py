"""
Data models for assistant module.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SearchResult:
    """Search result from anime resource websites."""

    title: str
    download_url: str
    is_downloaded: bool
    anime_name: Optional[str] = None
    episode: Optional[int] = None
    quality: Optional[str] = None


@dataclass
class DownloadResult:
    """Result of download operation."""

    success_count: int
    skipped_count: int
    failed_count: int
    success_items: List[str]
    skipped_items: List[tuple[str, str]]  # (title, reason)
    failed_items: List[tuple[str, str]]  # (title, error)

    def to_message(self) -> str:
        """Convert to user-friendly message."""
        msg = "✅ Download Summary:\n"
        msg += f"- Success: {self.success_count}\n"
        msg += f"- Skipped: {self.skipped_count}\n"
        msg += f"- Failed: {self.failed_count}\n\n"

        if self.success_items:
            msg += "✅ Successfully Downloaded:\n"
            for item in self.success_items:
                msg += f"  • {item}\n"

        if self.skipped_items:
            msg += "\n⏭️ Skipped Resources:\n"
            for title, reason in self.skipped_items:
                msg += f"  • {title}\n    Reason: {reason}\n"

        if self.failed_items:
            msg += "\n❌ Failed Resources:\n"
            for title, error in self.failed_items:
                msg += f"  • {title}\n    Error: {error}\n"

        return msg
