"""
Configuration manager for Download Organizer.
Handles app data paths, default settings, and JSON persistence.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("Sorty.Config")

APP_NAME = "Sorty"
APP_DISPLAY_NAME = "Sorty"
APP_VERSION = "1.0.0"

# Known Folder GUID for Downloads: {374DE290-123F-4565-9164-39C4925E467B}
GUID_DOWNLOADS = "{374DE290-123F-4565-9164-39C4925E467B}"


def get_default_downloads_folder() -> str:
    """
    Detect the Windows Downloads folder.
    Prioritizes dedicated/relocated downloads folders (e.g. D:\\downloads)
    then queries Windows Shell API SHGetKnownFolderPath, falling back to home dir.
    """
    # 1. Check common dedicated download directory on D: drive if present
    for candidate in [Path("D:/downloads"), Path("D:/Downloads"), Path("d:/downloads")]:
        if candidate.exists() and candidate.is_dir():
            return str(candidate.resolve())

    # 2. Query Windows Shell API for Downloads known folder
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        guid_str = GUID_DOWNLOADS.strip("{}")
        parts = guid_str.split("-")
        data1 = int(parts[0], 16)
        data2 = int(parts[1], 16)
        data3 = int(parts[2], 16)
        b = bytes.fromhex(parts[3] + parts[4])
        guid = GUID(data1, data2, data3, (wintypes.BYTE * 8)(*b))

        buf = ctypes.c_wchar_p()
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), 0, None, ctypes.byref(buf)
        )
        if hr == 0 and buf.value:
            path = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            if os.path.isdir(path):
                return str(Path(path).resolve())
    except Exception as exc:
        logger.debug("SHGetKnownFolderPath failed: %s; falling back to home dir", exc)

    fallback = Path.home() / "Downloads"
    return str(fallback.resolve())



def get_app_data_dir() -> Path:
    """
    Get the application data directory: %APPDATA%\\Sorty.
    Migrates previous DownloadOrganizer data if available.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        base = Path.home() / "AppData" / "Roaming"
    data_dir = base / APP_NAME
    data_dir.mkdir(parents=True, exist_ok=True)

    # Seamless migration from DownloadOrganizer
    old_dir = base / "DownloadOrganizer"
    if old_dir.exists():
        import shutil
        old_db = old_dir / "history.db"
        new_db = data_dir / "history.db"
        if old_db.exists() and not new_db.exists():
            try:
                shutil.copy2(old_db, new_db)
            except Exception:
                pass
        old_cfg = old_dir / "config.json"
        new_cfg = data_dir / "config.json"
        if old_cfg.exists() and not new_cfg.exists():
            try:
                shutil.copy2(old_cfg, new_cfg)
            except Exception:
                pass

    return data_dir


def get_logs_dir() -> Path:
    """
    Get the application logs directory: %APPDATA%\\DownloadOrganizer\\logs.
    """
    logs_dir = get_app_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_db_path() -> Path:
    """
    Get the path to SQLite history database: %APPDATA%\\DownloadOrganizer\\history.db.
    """
    return get_app_data_dir() / "history.db"


def get_config_path() -> Path:
    """
    Get the path to config.json: %APPDATA%\\DownloadOrganizer\\config.json.
    """
    return get_app_data_dir() / "config.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "downloads_folder": "",  # populated on init
    "auto_organize": True,
    "review_mode": False,
    "notifications": True,
    "start_with_windows": False,
    "run_minimized": False,
    "theme": "system",  # 'system', 'light', 'dark'
    "organization_delay": 2,  # seconds
    "duplicate_handling": "rename_automatically",
    "history_retention": "forever",  # '30_days', '90_days', '1_year', 'forever'
    "run_in_background": True,
    "first_run_completed": False,
    "paused": False,
}


class ConfigManager:
    """
    Thread-safe configuration manager for reading and persisting user preferences.
    """

    def __init__(self, config_file: Optional[Path] = None):
        self.config_path = config_file or get_config_path()
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk, creating defaults if missing."""
        data = dict(DEFAULT_CONFIG)
        data["downloads_folder"] = get_default_downloads_folder()

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        data.update(saved)
            except Exception as exc:
                logger.error("Failed to read config from %s: %s", self.config_path, exc)

        self._data = data
        return self._data

    def save(self) -> bool:
        """Persist current settings to disk."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4)
            # Atomic replace
            os.replace(temp_path, self.config_path)
            return True
        except Exception as exc:
            logger.error("Failed to save config to %s: %s", self.config_path, exc)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def update(self, new_data: Dict[str, Any]) -> None:
        self._data.update(new_data)
        self.save()

    @property
    def downloads_folder(self) -> str:
        folder = self.get("downloads_folder")
        if not folder or not os.path.exists(folder):
            folder = get_default_downloads_folder()
            self.set("downloads_folder", folder)
        return folder

    @property
    def auto_organize(self) -> bool:
        return bool(self.get("auto_organize", True))

    @property
    def review_mode(self) -> bool:
        return bool(self.get("review_mode", False))

    @property
    def notifications(self) -> bool:
        return bool(self.get("notifications", True))

    @property
    def start_with_windows(self) -> bool:
        return bool(self.get("start_with_windows", False))

    @property
    def run_minimized(self) -> bool:
        return bool(self.get("run_minimized", False))

    @property
    def theme(self) -> str:
        return str(self.get("theme", "system"))

    @property
    def organization_delay(self) -> int:
        return int(self.get("organization_delay", 2))

    @property
    def paused(self) -> bool:
        return bool(self.get("paused", False))

    @property
    def run_in_background(self) -> bool:
        return bool(self.get("run_in_background", True))

    @property
    def first_run_completed(self) -> bool:
        return bool(self.get("first_run_completed", False))
