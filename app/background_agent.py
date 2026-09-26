"""
BackgroundAgent module for Download Organizer.
Exposes BackgroundAgent, DownloadWatcher, and related types.
"""

from app.watcher import (
    AgentStatus,
    BackgroundAgent,
    DownloadWatcher,
    FileState,
    PendingItem,
    TEMP_DOWNLOAD_EXTENSIONS,
    WatcherEventHandler,
    WatcherStatus,
)

__all__ = [
    "AgentStatus",
    "BackgroundAgent",
    "DownloadWatcher",
    "FileState",
    "PendingItem",
    "TEMP_DOWNLOAD_EXTENSIONS",
    "WatcherEventHandler",
    "WatcherStatus",
]
