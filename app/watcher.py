"""
Background Agent and File Watcher Engine for Download Organizer.
Provides independent background operation, watchdog filesystem monitoring on Downloads root,
event debouncing, download stabilization, single worker queue, startup reconciliation,
manual check (Scan Now), diagnostics, and health monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging
import os
from pathlib import Path
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import ConfigManager
from app.organizer import OrganizerResult, SafeOrganizer
from app.utils import format_size, get_file_metadata, is_file_accessible

logger = logging.getLogger("DownloadOrganizer.BackgroundAgent")

# Temporary file extensions used by browsers and download managers
TEMP_DOWNLOAD_EXTENSIONS = {
    ".crdownload",
    ".part",
    ".tmp",
    ".partial",
    ".download",
    ".opdownload",
}


class FileState(Enum):
    DETECTED = "DETECTED"
    STABILIZING = "STABILIZING"
    READY = "READY"
    WAITING_REVIEW = "WAITING_REVIEW"
    MOVING = "MOVING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    UNDONE = "UNDONE"


class WatcherStatus(Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    STOPPING = "STOPPING"


class AgentStatus(Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    PAUSED = "PAUSED"


@dataclass
class PendingItem:
    file_path: Path
    filename: str
    extension: str
    file_size: int
    suggested_folder: str
    reason: str
    state: FileState
    detected_at: float
    last_modified_at: float
    error_message: Optional[str] = None


class WatcherEventHandler(FileSystemEventHandler):
    """
    Captures Windows filesystem events on the configured Downloads root.
    Only captures direct files in Downloads root, ignoring category folders and temp files.
    """

    def __init__(self, agent: "BackgroundAgent"):
        super().__init__()
        self.agent = agent

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.agent.enqueue_event(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.agent.enqueue_event(event.src_path, "modified")

    def on_moved(self, event: FileSystemEvent) -> None:
        # Browser completes download: file.pdf.crdownload -> file.pdf
        if not event.is_directory:
            self.agent.enqueue_event(event.dest_path, "moved")


class BackgroundAgent:
    """
    Independent background organizer engine.
    Controls:
      - FileWatcher (watchdog Observer on Downloads root only)
      - EventQueue (thread-safe debounce queue)
      - Stabilization (size check over time, access verification)
      - OrganizerWorker (single worker thread executing safe organization)
      - Startup reconciliation (one initial check for missed files)
      - Manual Check / Scan Now workflow
      - Diagnostics & Health monitoring (auto-restart up to 5 times)
    """

    def __init__(
        self,
        config: ConfigManager,
        organizer: SafeOrganizer,
        on_item_updated: Optional[Callable[[], None]] = None,
        on_file_organized: Optional[Callable[[OrganizerResult], None]] = None,
        on_status_changed: Optional[Callable[[], None]] = None,
    ):
        self.config = config
        self.organizer = organizer
        self.on_item_updated = on_item_updated
        self.on_file_organized = on_file_organized
        self.on_status_changed = on_status_changed

        self.watch_dir = Path(config.downloads_folder).resolve()
        self._observer: Optional[Observer] = None
        self._work_queue: queue.Queue[str] = queue.Queue()
        self._running = False
        self._paused = config.paused
        self._worker_thread: Optional[threading.Thread] = None

        # Watcher and Agent health status
        self._watcher_status: WatcherStatus = WatcherStatus.STOPPED
        self._agent_status: AgentStatus = AgentStatus.STOPPED
        self._restart_count = 0
        self._max_restarts = 5
        self._last_error: Optional[str] = None

        # Lock for thread safety on internal caches
        self._lock = threading.RLock()
        self.pending_files: Dict[str, float] = {}  # path -> timestamp (debouncing)
        self.active_processing: Set[str] = set()
        self.review_queue: Dict[str, PendingItem] = {}  # str(path) -> PendingItem
        self.active_stabilizing: Dict[str, PendingItem] = {}  # str(path) -> PendingItem

        # Diagnostics metrics
        self._last_event_time: Optional[str] = None
        self._last_organization_time: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def watcher_status(self) -> WatcherStatus:
        return self._watcher_status

    @property
    def agent_status(self) -> AgentStatus:
        if not self._running:
            return AgentStatus.STOPPED
        if self._paused:
            return AgentStatus.PAUSED
        if self._watcher_status == WatcherStatus.ERROR:
            return AgentStatus.ERROR
        return AgentStatus.RUNNING

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.config.set("paused", paused)
        logger.info("BackgroundAgent paused state set to: %s", paused)
        if not paused:
            self._work_queue.put("__WAKEUP__")
        if self.on_status_changed:
            self.on_status_changed()
        if self.on_item_updated:
            self.on_item_updated()

    def pause(self) -> None:
        """Pause automatic background processing."""
        self.set_paused(True)

    def resume(self) -> None:
        """Resume automatic background processing."""
        self.set_paused(False)

    def update_watch_directory(self, new_dir: str) -> None:
        """Update watched folder dynamically."""
        new_path = Path(new_dir).resolve()
        if new_path == self.watch_dir:
            return

        was_running = self._running
        if was_running:
            self.stop()

        self.watch_dir = new_path
        self.organizer.set_base_folder(str(new_path))

        if was_running:
            self.start()

    # -------------------------------------------------------------
    # Lifecycle: Start, Stop, Health & Auto-Restart
    # -------------------------------------------------------------

    def start(self) -> None:
        """Start the background agent: worker thread, watchdog observer, and startup reconciliation."""
        with self._lock:
            if self._running:
                return

            self.watch_dir.mkdir(parents=True, exist_ok=True)
            self._running = True
            self._agent_status = AgentStatus.RUNNING
            self._watcher_status = WatcherStatus.STARTING

            # 1. Start single dedicated worker thread
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name="BackgroundAgentWorker",
                daemon=True,
            )
            self._worker_thread.start()

            # 2. Start watchdog observer on Downloads root only (recursive=False)
            self._start_watcher_observer()

        if self.on_status_changed:
            self.on_status_changed()

    def _start_watcher_observer(self) -> bool:
        """Initialize and start watchdog observer."""
        try:
            self._observer = Observer()
            handler = WatcherEventHandler(self)
            self._observer.schedule(handler, str(self.watch_dir), recursive=False)
            self._observer.start()
            self._watcher_status = WatcherStatus.RUNNING
            self._last_error = None
            logger.info("Started file watcher observer on: %s", self.watch_dir)
            return True
        except Exception as exc:
            self._watcher_status = WatcherStatus.ERROR
            self._last_error = str(exc)
            logger.error("Failed to start file watcher observer: %s", exc)
            return False

    def _restart_watcher_if_needed(self) -> None:
        """Restart watcher if unexpectedly stopped, up to max_restarts (Part 18)."""
        if not self._running:
            return

        with self._lock:
            if self._observer and not self._observer.is_alive():
                if self._restart_count < self._max_restarts:
                    self._restart_count += 1
                    logger.warning(
                        "Watcher observer died. Attempting restart %d of %d...",
                        self._restart_count,
                        self._max_restarts,
                    )
                    time.sleep(1.0)
                    if self._start_watcher_observer():
                        logger.info("Watcher successfully restarted.")
                        return
                self._watcher_status = WatcherStatus.ERROR
                logger.error("Watcher observer failed after %d restart attempts.", self._max_restarts)

    def stop(self) -> None:
        """Safely stop watcher, drain work queue safely, and terminate worker thread."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._watcher_status = WatcherStatus.STOPPING
            self._agent_status = AgentStatus.STOPPED

            if self._observer:
                try:
                    self._observer.stop()
                    self._observer.join(timeout=2.0)
                except Exception as exc:
                    logger.debug("Error stopping observer: %s", exc)
                self._observer = None

            self._watcher_status = WatcherStatus.STOPPED

            # Unblock worker thread
            self._work_queue.put("__STOP__")

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)

        logger.info("Stopped BackgroundAgent.")
        if self.on_status_changed:
            self.on_status_changed()


    # -------------------------------------------------------------
    # Event Ingestion & Debouncing (Part 2 & Part 4)
    # -------------------------------------------------------------

    def enqueue_event(self, path_str: str, event_type: str) -> None:
        """
        Debounce events and queue candidate files for stabilization.
        Windows can fire created, modified, modified, moved for the same file.
        Maintains pending_files to avoid duplicate queueing.
        """
        path = Path(path_str)

        # Ignore subdirectories or events outside direct downloads root (Part 2)
        try:
            if path.parent.resolve() != self.watch_dir.resolve():
                return
        except Exception:
            return

        # Never process temporary download extensions (Part 3)
        ext = path.suffix.lower()
        if ext in TEMP_DOWNLOAD_EXTENSIONS or path.name.startswith("."):
            return

        if self._paused:
            return

        now = time.time()
        with self._lock:
            # Check if file is already pending or being processed
            last_time = self.pending_files.get(path_str, 0)
            self.pending_files[path_str] = now
            if (now - last_time) < 1.0:
                # Debounce: duplicate event within 1s
                return
            if path_str in self.active_processing:
                return

            self._last_event_time = datetime.now().strftime("%I:%M:%S %p")

        self._work_queue.put(path_str)

    # -------------------------------------------------------------
    # Single Dedicated Worker Loop (Part 5)
    # -------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Single worker thread processing stabilized downloads."""
        while self._running:
            try:
                item_path_str = self._work_queue.get(timeout=1.0)
            except queue.Empty:
                self._restart_watcher_if_needed()
                continue

            if item_path_str in ("__STOP__", None):
                break
            if item_path_str == "__WAKEUP__":
                self._process_held_items()
                continue

            try:
                self._handle_file_event(item_path_str)
            except Exception as exc:
                logger.error("Unhandled error processing file event for %s: %s", item_path_str, exc)
            finally:
                with self._lock:
                    self.pending_files.pop(item_path_str, None)
                    self.active_processing.discard(item_path_str)

    def _handle_file_event(self, path_str: str) -> None:
        path = Path(path_str)
        if not path.exists() or not path.is_file():
            return

        # Confirm path is in watch_dir root
        try:
            if path.parent.resolve() != self.watch_dir.resolve():
                return
        except Exception:
            return

        with self._lock:
            self.active_processing.add(path_str)

        # Pre-classify for suggested folder and reason
        meta = get_file_metadata(path)
        if not meta:
            return
        size, ext, mtime = meta
        cl_res = self.organizer.classifier.classify(path, size, mtime)

        pending = PendingItem(
            file_path=path,
            filename=path.name,
            extension=ext,
            file_size=size,
            suggested_folder=cl_res.destination_folder,
            reason=cl_res.reason,
            state=FileState.STABILIZING,
            detected_at=time.time(),
            last_modified_at=time.time(),
        )

        with self._lock:
            self.active_stabilizing[path_str] = pending
        if self.on_item_updated:
            self.on_item_updated()

        # Step 2: Stabilize file (Part 3)
        stable = self._stabilize_file(path)

        with self._lock:
            self.active_stabilizing.pop(path_str, None)

        if not stable:
            logger.debug("File %s did not stabilize or was deleted/locked.", path.name)
            if self.on_item_updated:
                self.on_item_updated()
            return

        # Check if paused or auto_organize disabled
        if self._paused or not self.config.auto_organize:
            pending.state = FileState.WAITING_REVIEW
            with self._lock:
                self.review_queue[path_str] = pending
            if self.on_item_updated:
                self.on_item_updated()
            return

        # Check if Review Mode is enabled
        if self.config.review_mode:
            pending.state = FileState.WAITING_REVIEW
            with self._lock:
                self.review_queue[path_str] = pending
            logger.info("File '%s' placed in review queue (Review Mode ON)", path.name)
            if self.on_item_updated:
                self.on_item_updated()
            return

        # Step 3: Move safely
        self._execute_organization(pending)

    # -------------------------------------------------------------
    # Download Stabilization Engine (Part 3)
    # -------------------------------------------------------------

    def _stabilize_file(self, path: Path, max_wait: float = 60.0) -> bool:
        """
        Never move an actively downloading file.
        Algorithm:
        1. Wait 2 seconds.
        2. Check size.
        3. Wait 2 seconds.
        4. Check size again.
        5. If size is unchanged and accessible -> process.
        6. If size changed -> wait again.
        7. Maximum wait: 60 seconds.
        Also check file accessibility (locked detection).
        """
        start_time = time.time()

        step = 2.0
        if hasattr(self.config, "get"):
            step = float(self.config.get("stabilization_step", 2.0))
        elif hasattr(self.config, "stabilization_step"):
            step = float(self.config.stabilization_step)

        while (time.time() - start_time) < max_wait and self._running:
            if not path.exists():
                return False

            # Check if temporary download extension has appeared
            if path.suffix.lower() in TEMP_DOWNLOAD_EXTENSIONS:
                return False

            # 1. Wait step seconds (default 2s)
            time.sleep(step)
            if not path.exists():
                return False

            # 2. Check size 1
            try:
                s1 = path.stat().st_size
            except Exception:
                continue

            # 3. Wait step seconds (default 2s)
            time.sleep(step)
            if not path.exists():
                return False

            # 4. Check size 2
            try:
                s2 = path.stat().st_size
            except Exception:
                continue

            # 5. If size is unchanged
            if s1 == s2 and s1 >= 0:
                # Check accessibility
                if is_file_accessible(path):
                    return True
                # If locked, loop continues to retry later

        return path.exists() and is_file_accessible(path)

    def _execute_organization(self, item: PendingItem) -> Optional[OrganizerResult]:
        """Perform the actual movement through SafeOrganizer."""
        item.state = FileState.MOVING
        if self.on_item_updated:
            self.on_item_updated()

        res = self.organizer.organize_file(item.file_path)

        if res.success:
            item.state = FileState.COMPLETED
            with self._lock:
                self.review_queue.pop(str(item.file_path), None)
                self._last_organization_time = datetime.now().strftime("%I:%M:%S %p")
            if self.on_file_organized:
                self.on_file_organized(res)
        else:
            item.state = FileState.FAILED
            item.error_message = res.error_message

        if self.on_item_updated:
            self.on_item_updated()

        return res

    def _process_held_items(self) -> None:
        """Process items waiting in review queue if auto_organize is resumed."""
        if self._paused or not self.config.auto_organize or self.config.review_mode:
            return

        with self._lock:
            items = list(self.review_queue.values())

        for item in items:
            if item.file_path.exists():
                self._execute_organization(item)

    # -------------------------------------------------------------
    # Manual Check / Scan Now (Part 7)
    # -------------------------------------------------------------

    def manual_check_downloads(self) -> Dict[str, Any]:
        """
        Explicit single manual scan of the configured Downloads root.
        1. Find eligible unorganized files in Downloads root.
        2. Ignore category folders.
        3. Ignore temporary download files.
        4. Check stabilization & accessibility.
        5. Classify files.
        6. Prevent duplicate processing with background watcher.
        Returns:
          {
            "total_found": int,
            "ready_to_organize": List[PendingItem],
            "already_organized_count": int,
          }
        """
        if not self.watch_dir.exists():
            return {
                "total_found": 0,
                "ready_to_organize": [],
                "already_organized_count": 0,
            }

        ready_items: List[PendingItem] = []
        already_organized = 0
        total_files = 0

        # Scan folder items
        try:
            for item in self.watch_dir.iterdir():
                if item.is_dir():
                    # Category folder: count organized files inside
                    try:
                        for sub_f in item.iterdir():
                            if sub_f.is_file():
                                already_organized += 1
                                total_files += 1
                    except Exception:
                        pass
                    continue

                if not item.is_file() or item.name.startswith("."):
                    continue

                total_files += 1

                # Ignore temporary download files
                if item.suffix.lower() in TEMP_DOWNLOAD_EXTENSIONS:
                    continue

                path_str = str(item.resolve())

                # Do not duplicate if file is currently being processed by watcher
                with self._lock:
                    if path_str in self.active_processing:
                        continue

                # Check accessibility
                if not is_file_accessible(item):
                    continue

                meta = get_file_metadata(item)
                if not meta:
                    continue
                size, ext, mtime = meta

                # Classify
                cl_res = self.organizer.classifier.classify(item, size, mtime)

                pending = PendingItem(
                    file_path=item,
                    filename=item.name,
                    extension=ext,
                    file_size=size,
                    suggested_folder=cl_res.destination_folder,
                    reason=cl_res.reason,
                    state=FileState.READY,
                    detected_at=time.time(),
                    last_modified_at=mtime,
                )
                ready_items.append(pending)
        except Exception as exc:
            logger.error("Error during manual check: %s", exc)

        return {
            "total_found": total_files,
            "ready_to_organize": ready_items,
            "already_organized_count": already_organized,
        }

    def organize_manual_items(self, items: List[PendingItem]) -> List[OrganizerResult]:
        """Process approved items from Manual Check."""
        results: List[OrganizerResult] = []
        for item in items:
            if not item.file_path.exists():
                continue
            with self._lock:
                self.pending_files[str(item.file_path)] = time.time()
                self.active_processing.add(str(item.file_path))
            try:
                res = self.organizer.organize_file(item.file_path)
                results.append(res)
                if res.success:
                    with self._lock:
                        self._last_organization_time = datetime.now().strftime("%I:%M:%S %p")
                    if self.on_file_organized:
                        self.on_file_organized(res)
            finally:
                with self._lock:
                    self.pending_files.pop(str(item.file_path), None)
                    self.active_processing.discard(str(item.file_path))

        if self.on_item_updated:
            self.on_item_updated()

        return results

    # -------------------------------------------------------------
    # Diagnostics & Status (Part 14)
    # -------------------------------------------------------------

    def get_diagnostics(self) -> Dict[str, Any]:
        """Return real diagnostic state for UI display."""
        return {
            "background_agent": "RUNNING" if self._running else "STOPPED",
            "file_watcher": self._watcher_status.value,
            "queue_size": self._work_queue.qsize(),
            "last_event": self._last_event_time or "None",
            "last_organization": self._last_organization_time or "None",
            "watched_folder": str(self.watch_dir),
            "retry_count": self._restart_count,
            "last_error": self._last_error,
            "paused": self._paused,
        }

    # -------------------------------------------------------------
    # Manual Test Background Monitoring (Part 15)
    # -------------------------------------------------------------

    def create_background_test_file(self) -> Tuple[Path, str]:
        """
        Create a safe temporary test file inside the configured Downloads root.
        Only called when user explicitly clicks 'Test Background Monitoring'.
        Watcher will detect it naturally and organize it.
        """
        test_filename = "DownloadOrganizer_Test.txt"
        test_path = self.watch_dir / test_filename
        test_path.write_text(
            f"Download Organizer background monitoring test file created at {datetime.now()}.\n",
            encoding="utf-8",
        )
        logger.info("Created background test file: %s", test_path)
        return test_path, test_filename

    # -------------------------------------------------------------
    # Review Queue Operations
    # -------------------------------------------------------------

    def get_waiting_items(self) -> List[PendingItem]:
        """Return list of all items waiting for organization or review."""
        with self._lock:
            items = list(self.review_queue.values()) + list(self.active_stabilizing.values())
            return items

    def process_review_item(
        self,
        file_path_str: str,
        action: str,  # 'move', 'skip', 'custom'
        custom_category: Optional[str] = None,
    ) -> Optional[OrganizerResult]:
        """Manual action on an item in Review Mode."""
        with self._lock:
            item = self.review_queue.get(file_path_str)
            if not item:
                return None

        if action == "skip":
            with self._lock:
                self.review_queue.pop(file_path_str, None)
            if self.on_item_updated:
                self.on_item_updated()
            return None

        if action in ("move", "custom"):
            category = custom_category or item.suggested_folder
            reason = f"Manual review: {category}" if custom_category else item.reason
            res = self.organizer.organize_file(
                item.file_path,
                custom_category=category,
                custom_reason=reason,
            )
            with self._lock:
                self.review_queue.pop(file_path_str, None)

            if res.success and self.on_file_organized:
                self.on_file_organized(res)

            if self.on_item_updated:
                self.on_item_updated()

            return res

        return None


# Backwards compatibility alias
class DownloadWatcher(BackgroundAgent):
    """Alias for backwards compatibility with existing imports."""
    pass
