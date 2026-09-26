"""
Utility functions for Download Organizer.
Provides path safety, duplicate filename generation, file lock detection, and formatting.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("DownloadOrganizer.Utils")


def get_windows_downloads_folder() -> str:
    """
    Detect the Windows Downloads folder using the Windows Shell API.
    Falls back to Path.home() / 'Downloads'.
    """
    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

        # FOLDERID_Downloads: {374DE290-123F-4565-9164-39C4925E467B}
        guid_str = "374DE290-123F-4565-9164-39C4925E467B"
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
        logger.debug("SHGetKnownFolderPath query failed: %s", exc)

    fallback = Path.home() / "Downloads"
    return str(fallback.resolve())


def is_safe_path(base_dir: str | Path, target_path: str | Path) -> bool:
    """
    Prevent path traversal.
    Ensure resolved target_path is within base_dir or a valid absolute path.
    """
    try:
        resolved_base = Path(base_dir).resolve()
        resolved_target = Path(target_path).resolve()
        # Check if target is equal to base or is a child of base
        return resolved_target == resolved_base or resolved_base in resolved_target.parents
    except Exception:
        return False


def get_unique_destination_path(destination_dir: str | Path, filename: str) -> Path:
    """
    Generate a non-conflicting destination path.
    Preserves extensions and handles multi-part names.
    Examples:
        resume.pdf -> resume.pdf
        if exists: resume (1).pdf -> resume (2).pdf
        project.backup.zip -> project.backup (1).zip (not project.backup.zip (1))
    """
    dest_dir = Path(destination_dir)
    target = dest_dir / filename

    if not target.exists():
        return target

    # Split stem and suffix
    orig_path = Path(filename)
    suffix = orig_path.suffix
    stem = orig_path.stem

    counter = 1
    while True:
        candidate_name = f"{stem} ({counter}){suffix}"
        candidate_path = dest_dir / candidate_name
        if not candidate_path.exists():
            return candidate_path
        counter += 1


def is_file_accessible(file_path: str | Path) -> bool:
    """
    Verify that the file is not currently locked or being written to by another process.
    Does NOT modify or execute the file.
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return False

    # Attempt to open for read access
    try:
        with open(path, "rb") as f:
            f.read(1)
    except (PermissionError, OSError):
        return False

    # Check Windows file sharing lock by attempting a rename to its own name
    # On Windows, if a file has an active exclusive write lock, rename fails with WinError 32
    try:
        os.rename(path, path)
        return True
    except (PermissionError, OSError):
        return False


def format_size(num_bytes: int) -> str:
    """Format bytes into human-readable size (e.g., 2.4 MB)."""
    if num_bytes < 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(num_bytes)} {unit}"
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def get_file_metadata(file_path: str | Path) -> Optional[Tuple[int, str, float]]:
    """
    Get file size, extension, and modification time safely.
    Returns (size_bytes, extension_with_dot, mtime) or None on error.
    """
    try:
        p = Path(file_path)
        stat = p.stat()
        return (stat.st_size, p.suffix.lower(), stat.st_mtime)
    except Exception:
        return None


def set_start_with_windows(enable: bool, app_exe_or_script: Optional[str] = None) -> bool:
    """
    Manage HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run registry key.
    Requires ZERO administrator privileges. Starts minimized to system tray.
    """
    import sys
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_names = ["Sorty", "DownloadOrganizer"]

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                if app_exe_or_script:
                    target = app_exe_or_script
                elif getattr(sys, "frozen", False):
                    target = f'"{sys.executable}" --minimized'
                else:
                    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
                    target = f'"{python_exe}" "{Path(__file__).resolve().parent / "main.py"}" --minimized'
                winreg.SetValueEx(key, "Sorty", 0, winreg.REG_SZ, target)
                logger.info("Enabled autostart with Windows: %s", target)
            else:
                for name in app_names:
                    try:
                        winreg.DeleteValue(key, name)
                        logger.info("Disabled autostart with Windows for %s", name)
                    except FileNotFoundError:
                        pass
        return True
    except Exception as exc:
        logger.warning("Failed to update Windows autostart registry key: %s", exc)
        return False


def is_start_with_windows_enabled() -> bool:
    """Check if the autostart registry entry exists."""
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    for name in ["Sorty", "DownloadOrganizer"]:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, name)
                if val:
                    return True
        except (FileNotFoundError, OSError):
            continue
    return False


def sync_recent_shortcuts(
    downloads_folder: str | Path,
    recent_items: Optional[dict] = None,
) -> Path:
    """
    Deprecated no-op. Per Part 8 & 24 specification:
    Download Organizer NEVER creates a physical Recent directory or shortcuts.
    Recent is purely a virtual database-backed view.
    """
    return Path(downloads_folder)


