"""
Lightweight Windows notification manager for Download Organizer.
Supports debounced/batched notifications:
- Single file: 'Moved: resume.pdf → Resume'
- Multiple files: 'Organized 5 files.'
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Any, Callable, List, Optional

logger = logging.getLogger("DownloadOrganizer.Notifications")


class NotificationManager:
    """
    Manages non-intrusive Windows desktop notifications with batch debouncing.
    """

    def __init__(self, is_enabled_getter: Callable[[], bool], tray_notifier: Optional[Callable[[str, str], None]] = None):
        self.is_enabled_getter = is_enabled_getter
        self.tray_notifier = tray_notifier
        self._pending_items: List[str] = []
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def notify_organized(self, filename: str, category: str) -> None:
        """Queue an organization notification event."""
        if not self.is_enabled_getter():
            return

        with self._lock:
            self._pending_items.append(f"{filename} → {category}")
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(1.5, self._flush_notifications)
            self._timer.daemon = True
            self._timer.start()

    def _flush_notifications(self) -> None:
        with self._lock:
            items = list(self._pending_items)
            self._pending_items.clear()
            self._timer = None

        if not items:
            return

        if len(items) == 1:
            title = "Download Organizer"
            message = f"Moved: {items[0]}"
        else:
            title = "Download Organizer"
            message = f"Organized {len(items)} files."

        self.send_notification(title, message)

    def send_notification(self, title: str, message: str) -> None:
        """Dispatch notification via tray icon if present, or Windows toast."""
        if self.tray_notifier:
            try:
                self.tray_notifier(title, message)
                return
            except Exception as exc:
                logger.debug("Tray notifier failed: %s; trying Windows fallback", exc)

        self._show_windows_toast(title, message)

    def _show_windows_toast(self, title: str, message: str) -> None:
        """Lightweight Windows notification via PowerShell (non-blocking)."""
        clean_title = title.replace('"', '`"')
        clean_msg = message.replace('"', '`"')

        ps_script = (
            f"[void] [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
            f"$notify = New-Object System.Windows.Forms.NotifyIcon;"
            f"$notify.Icon = [System.Drawing.SystemIcons]::Information;"
            f"$notify.BalloonTipTitle = \"{clean_title}\";"
            f"$notify.BalloonTipText = \"{clean_msg}\";"
            f"$notify.Visible = $True;"
            f"$notify.ShowBalloonTip(3000);"
            f"Start-Sleep -Seconds 3;"
            f"$notify.Dispose();"
        )
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
        except Exception as exc:
            logger.debug("Windows balloon notification failed: %s", exc)
