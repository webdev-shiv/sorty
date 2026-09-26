"""
System tray integration for Download Organizer.
Provides background tray icon and quick context menu actions.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import threading
from typing import Callable, Optional

from PIL import Image
import pystray

logger = logging.getLogger("Sorty.Tray")


class TrayManager:
    """
    Manages the Windows notification area (system tray) icon and context menu.
    """

    def __init__(
        self,
        icon_path: str | Path,
        on_show_app: Callable[[], None],
        on_pause: Optional[Callable[[], None]] = None,
        on_resume: Optional[Callable[[], None]] = None,
        on_toggle_pause: Optional[Callable[[], None]] = None,
        on_open_downloads: Optional[Callable[[], None]] = None,
        on_open_settings: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        is_paused_getter: Optional[Callable[[], bool]] = None,
        on_undo_last: Optional[Callable[[], None]] = None,
        on_organize_now: Optional[Callable[[], None]] = None,
        on_check_downloads: Optional[Callable[[], None]] = None,
    ):
        self.icon_path = Path(icon_path)
        self.on_show_app = on_show_app or (lambda: None)
        self.on_organize_now = on_organize_now or (lambda: None)
        self.on_check_downloads = on_check_downloads or self.on_organize_now
        self.on_toggle_pause = on_toggle_pause
        self.on_open_downloads = on_open_downloads or (lambda: None)
        self.on_open_settings = on_open_settings or (lambda: None)
        self.on_exit = on_exit or (lambda: None)
        self.is_paused_getter = is_paused_getter or (lambda: False)
        self.on_undo_last = on_undo_last
        self.on_pause = on_pause
        self.on_resume = on_resume

        self._tray_icon: Optional[pystray.Icon] = None
        self._image: Optional[Image.Image] = None
        self._load_icon_image()

    def _load_icon_image(self) -> None:
        try:
            if self.icon_path.exists():
                self._image = Image.open(str(self.icon_path))
            else:
                self._image = Image.new("RGBA", (64, 64), color=(37, 99, 235, 255))
        except Exception as exc:
            logger.warning("Could not load tray icon from %s: %s", self.icon_path, exc)
            self._image = Image.new("RGBA", (64, 64), color=(37, 99, 235, 255))

    def _handle_pause(self) -> None:
        if self.on_pause:
            self.on_pause()
        elif self.on_toggle_pause and not self.is_paused_getter():
            self.on_toggle_pause()
        self.update_menu()

    def _handle_resume(self) -> None:
        if self.on_resume:
            self.on_resume()
        elif self.on_toggle_pause and self.is_paused_getter():
            self.on_toggle_pause()
        self.update_menu()

    def _build_menu(self) -> pystray.Menu:
        items = [
            pystray.MenuItem("Open", lambda icon, item: self.on_show_app(), default=True),
            pystray.MenuItem(
                "Pause Organization",
                lambda icon, item: self._handle_pause(),
                enabled=lambda item: not self.is_paused_getter(),
            ),
            pystray.MenuItem(
                "Resume Organization",
                lambda icon, item: self._handle_resume(),
                enabled=lambda item: self.is_paused_getter(),
            ),
            pystray.MenuItem("Open Downloads", lambda icon, item: self.on_open_downloads()),
            pystray.MenuItem("Settings", lambda icon, item: self.on_open_settings()),
            pystray.MenuItem("Exit", lambda icon, item: self._handle_exit()),
        ]

        return pystray.Menu(*items)

    def _handle_exit(self) -> None:
        self.stop()
        self.on_exit()

    def start(self) -> None:
        """Start the system tray icon in a background thread."""
        if self._tray_icon is not None:
            return

        def _run_tray():
            try:
                self._tray_icon = pystray.Icon(
                    name="Sorty",
                    icon=self._image,
                    title="Sorty - File Organizer",
                    menu=self._build_menu(),
                )
                self._tray_icon.run()
            except Exception as exc:
                logger.error("System tray error: %s", exc)


        tray_thread = threading.Thread(target=_run_tray, name="SystemTrayThread", daemon=True)
        tray_thread.start()
        logger.info("System tray initialized.")

    def update_menu(self) -> None:
        """Refresh the tray menu state (e.g. Pause/Resume text)."""
        if self._tray_icon:
            self._tray_icon.menu = self._build_menu()

    def notify(self, title: str, message: str) -> None:
        """Show balloon notification from tray icon."""
        if self._tray_icon:
            try:
                self._tray_icon.notify(message, title)
            except Exception as exc:
                logger.debug("pystray notify error: %s", exc)

    def stop(self) -> None:
        """Stop and remove tray icon."""
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception as exc:
                logger.debug("Error stopping tray icon: %s", exc)
            self._tray_icon = None
