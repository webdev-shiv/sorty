"""
Modern, lightweight Windows Desktop UI for Sorty.
Built with pure Tkinter + ttk.
ZERO AI or machine learning.
Crisp High-DPI rendering and streamlined user experience.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional
import webbrowser

from app.classifier import ClassificationResult, Classifier
from app.config import ConfigManager
from app.database import Database
from app.history import HistoryManager
from app.organizer import OrganizerResult, SafeOrganizer
from app.utils import (
    format_size,
    get_file_metadata,
    is_start_with_windows_enabled,
    set_start_with_windows,
)
from app.watcher import (
    AgentStatus,
    BackgroundAgent,
    DownloadWatcher,
    FileState,
    PendingItem,
    WatcherStatus,
)

logger = logging.getLogger("Sorty.UI")

LIGHT_THEME = {
    "bg_main": "#F8FAFC",
    "bg_card": "#FFFFFF",
    "bg_sidebar": "#F1F5F9",
    "fg_text": "#0F172A",
    "fg_muted": "#64748B",
    "border": "#E2E8F0",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_fg": "#FFFFFF",
    "success": "#16A34A",
    "warning": "#D97706",
    "danger": "#DC2626",
    "badge_bg": "#EFF6FF",
    "badge_fg": "#1D4ED8",
}

DARK_THEME = {
    "bg_main": "#0F172A",
    "bg_card": "#1E293B",
    "bg_sidebar": "#090D16",
    "fg_text": "#F8FAFC",
    "fg_muted": "#94A3B8",
    "border": "#334155",
    "accent": "#3B82F6",
    "accent_hover": "#60A5FA",
    "accent_fg": "#FFFFFF",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "badge_bg": "#1E3A8A",
    "badge_fg": "#93C5FD",
}


def get_file_type_icon(filename: str, category: str = "") -> str:
    """Return an intuitive emoji icon based on file extension and category."""
    ext = Path(filename).suffix.lower()
    cat_lower = category.lower()
    if ext == ".pdf":
        return "📕"
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff"):
        return "🖼️"
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"):
        return "🎬"
    if ext in (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"):
        return "🎵"
    if ext in (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"):
        return "📦"
    if ext in (".exe", ".msi", ".bat", ".cmd", ".com"):
        return "⚙️"
    if ext in (".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".h", ".json", ".sql", ".rs", ".go"):
        return "💻"
    if ext in (".doc", ".docx", ".txt", ".rtf", ".odt"):
        return "📄"
    if ext in (".xls", ".xlsx", ".csv", ".ods"):
        return "📊"
    if ext in (".ppt", ".pptx", ".odp"):
        return "📽️"
    if "college" in cat_lower:
        return "🎓"
    if "resume" in cat_lower:
        return "📑"
    if "invoice" in cat_lower or "receipt" in cat_lower:
        return "🧾"
    return "📁"


def format_recent_time(ts_str: str) -> str:
    """Format timestamp to e.g. 9:42 PM."""
    try:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        hour = dt.hour % 12 or 12
        ampm = "AM" if dt.hour < 12 else "PM"
        return f"{hour}:{dt.minute:02d} {ampm}"
    except Exception:
        return ts_str


class DownloadOrganizerApp:
    """
    Main Tkinter application window for Sorty.
    True background Windows utility with virtual Recent views.
    """

    def __init__(
        self,
        config: ConfigManager,
        db: Database,
        classifier: Classifier,
        organizer: SafeOrganizer,
        history: HistoryManager,
        watcher: DownloadWatcher,
        icon_path: Optional[str | Path] = None,
    ):
        self.config = config
        self.db = db
        self.classifier = classifier
        self.organizer = organizer
        self.history = history
        self.watcher = watcher
        self.background_agent = watcher
        self.icon_path = icon_path
        self.tray_manager = None

        # Check for old physical Recent folder in Downloads (Part 24)
        self._old_recent_dir = Path(self.config.downloads_folder) / "Recent"
        self._old_recent_found = self._old_recent_dir.exists() and self._old_recent_dir.is_dir()
        self._old_recent_dismissed = False

        self.root = tk.Tk()
        self.root.title("Sorty")
        self.root.geometry("1060x700")
        self.root.minsize(920, 600)

        # Set window icon
        self._apply_app_icon()

        # Theme colors
        self.colors = LIGHT_THEME
        self._resolve_theme()

        # State tracking
        self.current_page = "dashboard"
        self.nav_buttons: Dict[str, tk.Button] = {}

        # Build UI layout
        self._setup_styles()
        self._build_main_layout()

        # Handle window close: minimize to tray or exit based on run_in_background
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_requested)

        # Wire watcher callbacks
        self.watcher.on_item_updated = self._on_watcher_update_threadsafe
        self.watcher.on_file_organized = self._on_file_organized_threadsafe
        self.watcher.on_status_changed = lambda: self.root.after(0, self.update_status_indicator)

        # Initial view
        self.navigate("dashboard")

        # Periodically refresh status
        self._schedule_periodic_refresh()

    def _apply_app_icon(self) -> None:
        """Apply crisp application icon to window and taskbar."""
        base_dir = Path(__file__).resolve().parent.parent
        png_path = base_dir / "assets" / "icon.png"
        ico_path = base_dir / "assets" / "icon.ico"

        if png_path.exists():
            try:
                self._photo_icon = tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self._photo_icon)
            except Exception as exc:
                logger.debug("Failed setting iconphoto: %s", exc)

        if ico_path.exists():
            try:
                self.root.iconbitmap(str(ico_path))
            except Exception as exc:
                logger.debug("Failed setting iconbitmap: %s", exc)

    def _resolve_theme(self) -> None:
        th = self.config.theme.lower()
        if th == "dark":
            self.colors = DARK_THEME
        else:
            self.colors = LIGHT_THEME

    def _setup_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        c = self.colors
        self.root.configure(bg=c["bg_main"])

        style.configure(
            "Treeview",
            background=c["bg_card"],
            foreground=c["fg_text"],
            fieldbackground=c["bg_card"],
            rowheight=32,
            font=("Segoe UI", 9),
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=c["bg_sidebar"],
            foreground=c["fg_text"],
            font=("Segoe UI", 9, "bold"),
            borderwidth=1,
            relief="flat",
        )
        style.map("Treeview", background=[("selected", c["accent"])], foreground=[("selected", c["accent_fg"])])

    def _build_main_layout(self) -> None:
        self.main_container = tk.Frame(self.root, bg=self.colors["bg_main"])
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Sidebar
        self.sidebar = tk.Frame(self.main_container, bg=self.colors["bg_sidebar"], width=220)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self._build_sidebar()

        # Content Area
        self.content_frame = tk.Frame(self.main_container, bg=self.colors["bg_main"])
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=20, pady=16)

    def _build_sidebar(self) -> None:
        c = self.colors

        # App Brand Header
        brand_frame = tk.Frame(self.sidebar, bg=c["bg_sidebar"], pady=14, padx=14)
        brand_frame.pack(fill=tk.X)

        title_lbl = tk.Label(
            brand_frame,
            text="📁 Sorty",
            font=("Segoe UI", 15, "bold"),
            bg=c["bg_sidebar"],
            fg=c["fg_text"],
            anchor="w",
        )
        title_lbl.pack(fill=tk.X)

        sub_lbl = tk.Label(
            brand_frame,
            text="Smart File Organizer • 100% Local",
            font=("Segoe UI", 8),
            bg=c["bg_sidebar"],
            fg=c["fg_muted"],
            anchor="w",
        )
        sub_lbl.pack(fill=tk.X, pady=(2, 0))

        # Divider
        tk.Frame(self.sidebar, bg=c["border"], height=1).pack(fill=tk.X, padx=14, pady=2)

        # All 8 Main Navigation Items as Specified
        nav_items = [
            ("dashboard", "📊  Dashboard"),
            ("recent", "🕒  Recent"),
            ("downloads", "📥  Downloads"),
            ("rules", "⚡  Rules"),
            ("categories", "🗂️  Categories"),
            ("history", "📜  History"),
            ("search", "🔍  Search"),
            ("settings", "⚙️  Settings"),
        ]

        self.nav_container = tk.Frame(self.sidebar, bg=c["bg_sidebar"], pady=6)
        self.nav_container.pack(fill=tk.BOTH, expand=True, padx=8)

        for page_id, label_text in nav_items:
            btn = tk.Button(
                self.nav_container,
                text=label_text,
                font=("Segoe UI", 9),
                anchor="w",
                padx=12,
                pady=6,
                relief=tk.FLAT,
                bd=0,
                bg=c["bg_sidebar"],
                fg=c["fg_text"],
                activebackground=c["border"],
                activeforeground=c["fg_text"],
                cursor="hand2",
                command=lambda pid=page_id: self.navigate(pid),
            )
            btn.pack(fill=tk.X, pady=1)
            self.nav_buttons[page_id] = btn

        # Bottom Panel: Active Folder & Auto-Organizer Status
        self.bottom_status_frame = tk.Frame(
            self.sidebar,
            bg=c["bg_card"],
            padx=10,
            pady=10,
            highlightbackground=c["border"],
            highlightthickness=1,
        )
        self.bottom_status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=10)

        folder_name = Path(self.config.downloads_folder).name or "Downloads"
        self.lbl_folder_sidebar = tk.Label(
            self.bottom_status_frame,
            text=f"📂 {folder_name}",
            font=("Segoe UI", 8, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
            anchor="w",
        )
        self.lbl_folder_sidebar.pack(fill=tk.X)

        self.status_indicator = tk.Label(
            self.bottom_status_frame,
            text="● Auto-Sort: Active",
            font=("Segoe UI", 8, "bold"),
            bg=c["bg_card"],
            fg=c["success"],
            anchor="w",
        )
        self.status_indicator.pack(fill=tk.X, pady=(4, 0))

        self.pause_btn = tk.Button(
            self.bottom_status_frame,
            text="Pause Auto-Sort",
            font=("Segoe UI", 8),
            relief=tk.FLAT,
            bg=c["bg_sidebar"],
            fg=c["fg_text"],
            cursor="hand2",
            command=self.toggle_pause,
            pady=3,
        )
        self.pause_btn.pack(fill=tk.X, pady=(4, 0))

    def _dismiss_old_recent_banner(self) -> None:
        self._old_recent_dismissed = True
        if hasattr(self, "_old_recent_banner_widget") and self._old_recent_banner_widget.winfo_exists():
            self._old_recent_banner_widget.destroy()

    def update_status_indicator(self) -> None:
        c = self.colors
        diag = self.watcher.get_diagnostics()
        watcher_stat = diag.get("file_watcher", "STOPPED")
        paused = diag.get("paused", False)

        if not self.watcher.is_running:
            status_text = "○ Background Disabled"
            status_fg = c["fg_muted"]
            btn_text = "▶ Start Auto-Sort"
        elif paused:
            status_text = "⏸ Organization Paused"
            status_fg = c["warning"]
            btn_text = "▶ Resume Auto-Sort"
        elif watcher_stat == "ERROR":
            status_text = "⚠️ Watcher: Error"
            status_fg = c["danger"]
            btn_text = "🔄 Retry Watcher"
        else:
            status_text = "● Background Active"
            status_fg = c["success"]
            btn_text = "⏸ Pause Auto-Sort"

        if hasattr(self, "status_indicator") and self.status_indicator.winfo_exists():
            self.status_indicator.config(text=status_text, fg=status_fg)
        if hasattr(self, "pause_btn") and self.pause_btn.winfo_exists():
            self.pause_btn.config(text=btn_text)

        folder_name = Path(self.config.downloads_folder).name or "Downloads"
        if hasattr(self, "lbl_folder_sidebar") and self.lbl_folder_sidebar.winfo_exists():
            self.lbl_folder_sidebar.config(text=f"📂 {folder_name}")

    def toggle_pause(self) -> None:
        new_state = not self.watcher.is_paused
        self.watcher.set_paused(new_state)
        self.update_status_indicator()
        if self.current_page == "dashboard":
            self.refresh_dashboard()

    def navigate(self, page_id: str) -> None:
        self.current_page = page_id
        c = self.colors

        # Highlight active button
        for pid, btn in self.nav_buttons.items():
            if pid == page_id:
                btn.config(bg=c["accent"], fg=c["accent_fg"], font=("Segoe UI", 9, "bold"))
            else:
                btn.config(bg=c["bg_sidebar"], fg=c["fg_text"], font=("Segoe UI", 9))

        # Clear content frame
        for child in self.content_frame.winfo_children():
            child.destroy()

        # Render chosen page
        if page_id == "dashboard":
            self._render_dashboard()
        elif page_id == "recent":
            self._render_recent_page()
        elif page_id == "downloads":
            self._render_downloads_page()
        elif page_id == "rules":
            self._render_rules_page()
        elif page_id == "categories":
            self._render_categories_page()
        elif page_id == "history":
            self._render_history_page()
        elif page_id == "search":
            self._render_search_page()
        elif page_id == "settings":
            self._render_settings_page()

    # =========================================================================
    # Page 1: Dashboard
    # =========================================================================

    def _render_dashboard(self) -> None:
        c = self.colors

        # Old Recent Folder Detection Notice (Part 24)
        if self._old_recent_found and not self._old_recent_dismissed:
            self._old_recent_banner_widget = tk.Frame(
                self.content_frame,
                bg="#FEF3C7",
                highlightbackground="#F59E0B",
                highlightthickness=1,
                padx=14,
                pady=8,
            )
            self._old_recent_banner_widget.pack(fill=tk.X, pady=(0, 12))

            tk.Label(
                self._old_recent_banner_widget,
                text="⚠️  An old Download Organizer 'Recent' folder was found in Downloads.",
                font=("Segoe UI", 9, "bold"),
                bg="#FEF3C7",
                fg="#92400E",
            ).pack(side=tk.LEFT)

            tk.Button(
                self._old_recent_banner_widget,
                text="Open Folder",
                font=("Segoe UI", 8, "bold"),
                bg="#F59E0B",
                fg="#FFFFFF",
                relief=tk.FLAT,
                padx=10,
                pady=2,
                cursor="hand2",
                command=lambda: os.startfile(str(self._old_recent_dir)),
            ).pack(side=tk.RIGHT, padx=4)

            tk.Button(
                self._old_recent_banner_widget,
                text="Ignore",
                font=("Segoe UI", 8),
                bg="#FEF3C7",
                fg="#92400E",
                relief=tk.SOLID,
                bd=1,
                padx=8,
                pady=2,
                cursor="hand2",
                command=self._dismiss_old_recent_banner,
            ).pack(side=tk.RIGHT, padx=4)

        # Header Title & Folder Banner
        header_frame = tk.Frame(self.content_frame, bg=c["bg_main"])
        header_frame.pack(fill=tk.X, pady=(0, 12))

        title = tk.Label(
            header_frame,
            text="Dashboard",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        )
        title.pack(side=tk.LEFT)

        folder_chip = tk.Frame(header_frame, bg=c["bg_card"], padx=10, pady=4, highlightbackground=c["border"], highlightthickness=1)
        folder_chip.pack(side=tk.RIGHT)

        cur_folder = self.config.downloads_folder
        folder_display = cur_folder if len(cur_folder) < 38 else "..." + cur_folder[-35:]
        tk.Label(
            folder_chip,
            text=f"📂 Active Folder: {folder_display}",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Button(
            folder_chip,
            text="Select Folder",
            font=("Segoe UI", 8, "bold"),
            bg=c["bg_sidebar"],
            fg=c["accent"],
            relief=tk.FLAT,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._change_downloads_folder,
        ).pack(side=tk.RIGHT)

        # Hero Action Buttons (Check Downloads, Undo Sort, Open Downloads)
        hero_frame = tk.Frame(self.content_frame, bg=c["bg_main"])
        hero_frame.pack(fill=tk.X, pady=(0, 14))

        btn_check_downloads = tk.Button(
            hero_frame,
            text="🔍  Check Downloads\nScan Downloads Root Now",
            font=("Segoe UI", 10, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            activebackground=c["accent_hover"],
            activeforeground=c["accent_fg"],
            relief=tk.FLAT,
            bd=0,
            padx=16,
            pady=12,
            cursor="hand2",
            command=self.check_downloads_dialog,
        )
        btn_check_downloads.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        btn_undo = tk.Button(
            hero_frame,
            text="↩️  Undo Sort\nRevert Last Organized Batch",
            font=("Segoe UI", 10, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_sidebar"],
            activeforeground=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=16,
            pady=12,
            cursor="hand2",
            command=self.handle_undo_last_batch,
        )
        btn_undo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

        btn_open = tk.Button(
            hero_frame,
            text="📂  Open Downloads\nExplore Sorted Files & Folders",
            font=("Segoe UI", 10, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_sidebar"],
            activeforeground=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=16,
            pady=12,
            cursor="hand2",
            command=self.open_downloads_folder,
        )
        btn_open.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # 5 Stats Cards (Part 12 & 13)
        stats_frame = tk.Frame(self.content_frame, bg=c["bg_main"])
        stats_frame.pack(fill=tk.X, pady=(0, 12))

        stats = self.db.get_stats()
        folder_size = self._calculate_downloads_size()
        waiting_count = len(self.watcher.get_waiting_items())

        if not self.watcher.is_running:
            status_val = "○ Disabled"
            status_sub = "Background: Off"
        elif self.watcher.is_paused:
            status_val = "⏸ Paused"
            status_sub = "Click to Resume"
        else:
            status_val = "● Active"
            status_sub = "Monitoring Downloads"

        card_defs = [
            ("Files Organized", str(stats.get("total_organized", 0)), "Files sorted safely"),
            ("Organized Today", str(stats.get("today_organized", 0)), "Since midnight"),
            ("Waiting", str(waiting_count), "In queue or review"),
            ("Downloads Size", format_size(folder_size), Path(self.config.downloads_folder).name or "Downloads"),
            ("Status", status_val, status_sub),
        ]

        for i, (card_title, card_val, card_sub) in enumerate(card_defs):
            card = tk.Frame(
                stats_frame,
                bg=c["bg_card"],
                highlightbackground=c["border"],
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3 if i > 0 else 0)

            tk.Label(card, text=card_title, font=("Segoe UI", 8), bg=c["bg_card"], fg=c["fg_muted"]).pack(anchor="w")

            val_fg = c["fg_text"]
            if "Active" in card_val:
                val_fg = c["success"]
            elif "Paused" in card_val:
                val_fg = c["warning"]
            elif "Disabled" in card_val:
                val_fg = c["fg_muted"]

            if card_title == "Status":
                val_lbl = tk.Label(card, text=card_val, font=("Segoe UI", 12, "bold"), bg=c["bg_card"], fg=val_fg, cursor="hand2")
                val_lbl.pack(anchor="w", pady=(2, 2))
                val_lbl.bind("<Button-1>", lambda e: self.toggle_pause())
            else:
                tk.Label(card, text=card_val, font=("Segoe UI", 12, "bold"), bg=c["bg_card"], fg=val_fg).pack(anchor="w", pady=(2, 2))
            tk.Label(card, text=card_sub, font=("Segoe UI", 7), bg=c["bg_card"], fg=c["fg_muted"]).pack(anchor="w")

        # SORTING PART: RECENT FOLDERS (Quick view without file duplication)
        recent_folders_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        recent_folders_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        sec_header = tk.Frame(recent_folders_card, bg=c["bg_card"])
        sec_header.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            sec_header,
            text="📁  Recent Sorted Folders",
            font=("Segoe UI", 11, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Label(
            sec_header,
            text="Click Open Folder to view sorted files directly • Zero file duplicates created",
            font=("Segoe UI", 8),
            bg=c["bg_card"],
            fg=c["fg_muted"],
        ).pack(side=tk.RIGHT)

        self.recent_folders_container = tk.Frame(recent_folders_card, bg=c["bg_card"])
        self.recent_folders_container.pack(fill=tk.BOTH, expand=True)
        self._populate_recent_folders()

        # DASHBOARD RECENT ACTIVITY (Latest 5 organized files with "View Recent" button)
        activity_subcard = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        activity_subcard.pack(fill=tk.X)

        act_title_bar = tk.Frame(activity_subcard, bg=c["bg_card"])
        act_title_bar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            act_title_bar,
            text="Recent Activity",
            font=("Segoe UI", 10, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Button(
            act_title_bar,
            text="View Recent →",
            font=("Segoe UI", 8, "bold"),
            bg=c["bg_sidebar"],
            fg=c["accent"],
            relief=tk.FLAT,
            cursor="hand2",
            command=lambda: self.navigate("recent"),
            padx=8,
            pady=2,
        ).pack(side=tk.RIGHT)

        tk.Button(
            act_title_bar,
            text="🔍  Check Downloads",
            font=("Segoe UI", 8, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self.check_downloads_dialog,
            padx=8,
            pady=2,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        self.recent_items_frame = tk.Frame(activity_subcard, bg=c["bg_card"])
        self.recent_items_frame.pack(fill=tk.X)
        self._populate_recent_activity()

    def _populate_recent_folders(self) -> None:
        """Show recently sorted destination folders with 1-click Open buttons."""
        c = self.colors
        for child in self.recent_folders_container.winfo_children():
            child.destroy()

        try:
            conn = self.db._get_connection()
            rows = conn.execute(
                """
                SELECT category, COUNT(*) as file_count, MAX(timestamp) as last_time
                FROM history
                WHERE status = 'success'
                GROUP BY category
                ORDER BY last_time DESC
                LIMIT 6
                """
            ).fetchall()
            conn.close()
            folder_stats = [dict(r) for r in rows]
        except Exception:
            folder_stats = []

        if not folder_stats:
            cats = self.db.get_categories()
            for cat in cats[:6]:
                folder_stats.append({
                    "category": cat["name"],
                    "file_count": 0,
                    "last_time": "Ready",
                })

        grid_frame = tk.Frame(self.recent_folders_container, bg=c["bg_card"])
        grid_frame.pack(fill=tk.BOTH, expand=True)

        for i, item in enumerate(folder_stats):
            cat_name = item["category"]
            cnt = item["file_count"]

            tile = tk.Frame(
                grid_frame,
                bg=c["bg_sidebar"],
                highlightbackground=c["border"],
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            row_idx = i // 3
            col_idx = i % 3
            tile.grid(row=row_idx, column=col_idx, sticky="nsew", padx=4, pady=4)
            grid_frame.columnconfigure(col_idx, weight=1)

            top_row = tk.Frame(tile, bg=c["bg_sidebar"])
            top_row.pack(fill=tk.X)

            icon_char = get_file_type_icon("", cat_name)
            tk.Label(
                top_row,
                text=f"{icon_char}  {cat_name}",
                font=("Segoe UI", 9, "bold"),
                bg=c["bg_sidebar"],
                fg=c["fg_text"],
                anchor="w",
            ).pack(side=tk.LEFT)

            count_text = f"{cnt} files" if cnt > 0 else "Folder"
            tk.Label(
                top_row,
                text=count_text,
                font=("Segoe UI", 7),
                bg=c["badge_bg"],
                fg=c["badge_fg"],
                padx=4,
                pady=1,
            ).pack(side=tk.RIGHT)

            cat_folder_path = Path(self.config.downloads_folder) / cat_name
            btn_open = tk.Button(
                tile,
                text="📂 Open Folder",
                font=("Segoe UI", 8),
                bg=c["bg_card"],
                fg=c["fg_text"],
                relief=tk.SOLID,
                bd=1,
                cursor="hand2",
                pady=2,
                command=lambda p=cat_folder_path: self._open_specific_folder(p),
            )
            btn_open.pack(fill=tk.X, pady=(6, 0))

    def _populate_recent_activity(self) -> None:
        """Populate latest 5 organized files in the Dashboard Recent Activity section."""
        c = self.colors
        for child in self.recent_items_frame.winfo_children():
            child.destroy()

        activities = self.history.get_recent_activity(limit=5)
        if not activities:
            tk.Label(
                self.recent_items_frame,
                text="No files organized yet. Newly downloaded files will appear here automatically.",
                font=("Segoe UI", 8, "italic"),
                bg=c["bg_card"],
                fg=c["fg_muted"],
                anchor="w",
            ).pack(fill=tk.X, pady=4)
            return

        for row in activities:
            item_row = tk.Frame(self.recent_items_frame, bg=c["bg_card"], pady=2)
            item_row.pack(fill=tk.X)

            status = row.get("status", "success")
            icon_text = "✓" if status == "success" else ("↩️" if status == "undone" else "❌")
            status_color = c["success"] if status == "success" else c["fg_muted"]

            tk.Label(
                item_row,
                text=icon_text,
                font=("Segoe UI", 9, "bold"),
                bg=c["bg_card"],
                fg=status_color,
                width=2,
            ).pack(side=tk.LEFT)

            info_frame = tk.Frame(item_row, bg=c["bg_card"])
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

            fname = row.get("filename", "")
            cat = row.get("category", "")
            ts = row.get("timestamp", "")
            time_display = format_recent_time(ts)

            text_line = f"{fname} → {cat}   ({time_display})"
            tk.Label(
                info_frame,
                text=text_line,
                font=("Segoe UI", 8),
                bg=c["bg_card"],
                fg=c["fg_text"],
                anchor="w",
            ).pack(fill=tk.X)

            if status == "success":
                hid = row.get("id")
                undo_btn = tk.Button(
                    item_row,
                    text="Undo",
                    font=("Segoe UI", 7, "bold"),
                    bg=c["bg_sidebar"],
                    fg=c["fg_text"],
                    relief=tk.SOLID,
                    bd=1,
                    padx=6,
                    pady=1,
                    cursor="hand2",
                    command=lambda h_id=hid: self.handle_undo(h_id),
                )
                undo_btn.pack(side=tk.RIGHT, padx=2)
            elif status == "undone":
                tk.Label(
                    item_row,
                    text="Undone",
                    font=("Segoe UI", 7, "italic"),
                    bg=c["bg_card"],
                    fg=c["fg_muted"],
                ).pack(side=tk.RIGHT, padx=4)

    # =========================================================================
    # Page 2: RECENT SECTION (Today & Yesterday Database-Backed Virtual View)
    # ZERO physical folder created. ZERO file copies.
    # =========================================================================

    def _render_recent_page(self) -> None:
        """
        Database-backed virtual view of files organized TODAY and YESTERDAY.
        Does NOT copy or duplicate any files. Queries SQLite history directly.
        """
        c = self.colors

        # Page Header
        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 10))

        title_box = tk.Frame(header, bg=c["bg_main"])
        title_box.pack(side=tk.LEFT)

        tk.Label(
            title_box,
            text="Recent",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Files organized today • Instant File Explorer Access (No duplicate files)",
            font=("Segoe UI", 9),
            bg=c["bg_main"],
            fg=c["fg_muted"],
        ).pack(anchor="w")

        # Top Right Actions: Open in File Explorer, Refresh, and 1-Click Undo
        actions_bar = tk.Frame(header, bg=c["bg_main"])
        actions_bar.pack(side=tk.RIGHT)

        tk.Button(
            actions_bar,
            text="📂  Open Downloads Folder",
            font=("Segoe UI", 8, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.open_downloads_folder,
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            actions_bar,
            text="🔄  Refresh",
            font=("Segoe UI", 8),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._render_recent_page,
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            actions_bar,
            text="↩️  Undo Last Sort",
            font=("Segoe UI", 8, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self.handle_undo_last_batch,
        ).pack(side=tk.LEFT, padx=3)

        # Scrollable container for TODAY and YESTERDAY sections
        container = tk.Frame(self.content_frame, bg=c["bg_main"])
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg=c["bg_main"], highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=c["bg_main"])

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Query Database for Today's and Yesterday's organized records (Part 8)
        recent_data = self.history.get_recent_organized(limit=200)
        today_items = recent_data.get("today", [])
        yesterday_items = recent_data.get("yesterday", [])

        # -------------------------------------------------------------
        # Section: TODAY
        # -------------------------------------------------------------
        self._build_recent_section(
            parent=scrollable_frame,
            section_title="TODAY",
            items=today_items,
            empty_msg="No files organized today yet. Downloads will appear here automatically when organized.",
        )

        tk.Frame(scrollable_frame, bg=c["bg_main"], height=16).pack(fill=tk.X)

        # -------------------------------------------------------------
        # Section: YESTERDAY
        # -------------------------------------------------------------
        self._build_recent_section(
            parent=scrollable_frame,
            section_title="YESTERDAY",
            items=yesterday_items,
            empty_msg="No files were organized yesterday.",
        )

    def _build_recent_section(
        self,
        parent: tk.Widget,
        section_title: str,
        items: List[Dict[str, Any]],
        empty_msg: str,
    ) -> None:
        """Render a section (TODAY or YESTERDAY) of recent organized files."""
        c = self.colors

        sec_bar = tk.Frame(parent, bg=c["bg_main"], pady=4)
        sec_bar.pack(fill=tk.X)

        tk.Label(
            sec_bar,
            text=section_title,
            font=("Segoe UI", 11, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        count_badge = f"{len(items)} file" if len(items) == 1 else f"{len(items)} files"
        tk.Label(
            sec_bar,
            text=count_badge,
            font=("Segoe UI", 8),
            bg=c["badge_bg"],
            fg=c["badge_fg"],
            padx=6,
            pady=1,
        ).pack(side=tk.LEFT, padx=8)

        card_container = tk.Frame(
            parent,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        card_container.pack(fill=tk.X)

        if not items:
            tk.Label(
                card_container,
                text=empty_msg,
                font=("Segoe UI", 9, "italic"),
                bg=c["bg_card"],
                fg=c["fg_muted"],
                anchor="w",
                pady=10,
            ).pack(fill=tk.X)
            return

        for idx, row in enumerate(items):
            if idx > 0:
                tk.Frame(card_container, bg=c["border"], height=1).pack(fill=tk.X, pady=6)

            item_id = row.get("id")
            fname = row.get("filename", "")
            cat = row.get("category", "")
            orig_path = row.get("original_path", "")
            dest_path = row.get("destination_path", "")
            reason = row.get("reason", "")
            ts = row.get("timestamp", "")
            fsize = row.get("file_size", 0)
            status = row.get("status", "success")

            time_str = format_recent_time(ts)
            size_str = format_size(fsize)
            icon_char = get_file_type_icon(fname, cat)

            row_frame = tk.Frame(card_container, bg=c["bg_card"])
            row_frame.pack(fill=tk.X, pady=2)

            # Left Icon
            tk.Label(
                row_frame,
                text=icon_char,
                font=("Segoe UI", 16),
                bg=c["bg_card"],
                width=3,
            ).pack(side=tk.LEFT, padx=(0, 8))

            # Main info column
            info_col = tk.Frame(row_frame, bg=c["bg_card"])
            info_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # Top Line: Timestamp • Filename • Category badge • Undone badge
            top_line = tk.Frame(info_col, bg=c["bg_card"])
            top_line.pack(fill=tk.X)

            tk.Label(
                top_line,
                text=time_str,
                font=("Segoe UI", 9, "bold"),
                bg=c["bg_card"],
                fg=c["fg_muted"],
            ).pack(side=tk.LEFT, padx=(0, 8))

            tk.Label(
                top_line,
                text=fname,
                font=("Segoe UI", 10, "bold"),
                bg=c["bg_card"],
                fg=c["fg_text"],
            ).pack(side=tk.LEFT)

            tk.Label(
                top_line,
                text=cat,
                font=("Segoe UI", 8),
                bg=c["badge_bg"],
                fg=c["badge_fg"],
                padx=6,
                pady=1,
            ).pack(side=tk.LEFT, padx=8)

            if status == "undone":
                tk.Label(
                    top_line,
                    text="Undone",
                    font=("Segoe UI", 8, "italic"),
                    bg=c["border"],
                    fg=c["danger"],
                    padx=6,
                    pady=1,
                ).pack(side=tk.LEFT, padx=2)

            # Current path based on status (undone reverts to orig_path)
            curr_path = orig_path if status == "undone" else dest_path
            orig_name = Path(orig_path).parent.name or "Downloads"
            curr_name = Path(curr_path).parent.name or cat
            path_display = f"{orig_name} → {curr_name}"

            sub_line = tk.Frame(info_col, bg=c["bg_card"])
            sub_line.pack(fill=tk.X, pady=(2, 0))

            tk.Label(
                sub_line,
                text=f"{path_display}   •   {size_str}   •   Reason: {reason}",
                font=("Segoe UI", 8),
                bg=c["bg_card"],
                fg=c["fg_muted"],
            ).pack(side=tk.LEFT)

            # Right Side: Action Buttons (Open File, Open Folder, Undo)
            btn_box = tk.Frame(row_frame, bg=c["bg_card"])
            btn_box.pack(side=tk.RIGHT, padx=4)

            tk.Button(
                btn_box,
                text="Open File",
                font=("Segoe UI", 8),
                bg=c["bg_sidebar"],
                fg=c["fg_text"],
                relief=tk.SOLID,
                bd=1,
                padx=8,
                pady=2,
                cursor="hand2",
                command=lambda p=curr_path: self._open_file_safe(p),
            ).pack(side=tk.LEFT, padx=2)

            tk.Button(
                btn_box,
                text="Open Folder",
                font=("Segoe UI", 8),
                bg=c["bg_sidebar"],
                fg=c["fg_text"],
                relief=tk.SOLID,
                bd=1,
                padx=8,
                pady=2,
                cursor="hand2",
                command=lambda p=curr_path: self._open_folder_and_select(p),
            ).pack(side=tk.LEFT, padx=2)

            if status == "success":
                tk.Button(
                    btn_box,
                    text="Undo",
                    font=("Segoe UI", 8, "bold"),
                    bg=c["bg_sidebar"],
                    fg=c["accent"],
                    relief=tk.SOLID,
                    bd=1,
                    padx=8,
                    pady=2,
                    cursor="hand2",
                    command=lambda hid=item_id: self._handle_recent_undo(hid),
                ).pack(side=tk.LEFT, padx=2)

            # Context menu for clicking item row
            def _show_context_menu(event, p=curr_path, hid=item_id, s=status):
                menu = tk.Menu(self.root, tearoff=0)
                menu.add_command(label="Open File", command=lambda: self._open_file_safe(p))
                menu.add_command(label="Open Folder", command=lambda: self._open_folder_and_select(p))
                if s == "success":
                    menu.add_separator()
                    menu.add_command(label="Undo", command=lambda: self._handle_recent_undo(hid))
                try:
                    menu.tk_popup(event.x_root, event.y_root)
                finally:
                    menu.grab_release()

            row_frame.bind("<Button-3>", _show_context_menu)
            row_frame.bind("<Double-Button-1>", lambda e, p=curr_path: self._open_file_safe(p))

    def _handle_recent_undo(self, history_id: int) -> None:
        """Handle undo from the Recent page and immediately refresh the view."""
        success, msg = self.history.undo_move(history_id)
        if success:
            messagebox.showinfo("Undo Successful", msg)
        else:
            messagebox.showwarning("Undo Notice", msg)
        self._render_recent_page()

    def _open_recent_folder_in_explorer(self) -> None:
        """Open Downloads folder directly in Windows File Explorer."""
        self.open_downloads_folder()

    def _open_file_safe(self, file_path_str: str) -> None:
        """Safely open file with default Windows associated application."""
        p = Path(file_path_str)
        if not p.exists():
            messagebox.showwarning(
                "File Not Found",
                f"The file no longer exists at:\n{file_path_str}\n\nIt may have been moved or deleted.",
            )
            return
        try:
            os.startfile(str(p))
        except Exception as exc:
            messagebox.showerror("Error Opening File", f"Could not open file: {exc}")

    def _open_folder_and_select(self, file_path_str: str) -> None:
        """Open Windows Explorer and highlight/select the file."""
        p = Path(file_path_str)
        if p.exists():
            try:
                subprocess.Popen(["explorer.exe", f"/select,{str(p.resolve())}"])
                return
            except Exception:
                pass
        parent = p.parent
        if parent.exists():
            try:
                os.startfile(str(parent.resolve()))
            except Exception as exc:
                messagebox.showerror("Error Opening Folder", f"Could not open folder: {exc}")
        else:
            messagebox.showwarning("Folder Not Found", f"Directory does not exist:\n{parent}")

    # =========================================================================
    # Page 3: Downloads Page
    # =========================================================================

    def _render_downloads_page(self) -> None:
        c = self.colors

        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="Downloads Folder",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text=f"Monitored: {self.config.downloads_folder}",
            font=("Segoe UI", 9),
            bg=c["bg_main"],
            fg=c["fg_muted"],
        ).pack(side=tk.LEFT, padx=12, pady=(4, 0))

        toolbar = tk.Frame(self.content_frame, bg=c["bg_main"])
        toolbar.pack(fill=tk.X, pady=(0, 10))

        tk.Button(
            toolbar,
            text="🔍  Check Downloads",
            font=("Segoe UI", 9, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            padx=14,
            pady=5,
            cursor="hand2",
            command=self.check_downloads_dialog,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            toolbar,
            text="⚡  Organize All Now",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.manual_organize_now,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            toolbar,
            text="📂  Open in Explorer",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self.open_downloads_folder,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            toolbar,
            text="🔄  Refresh List",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._populate_downloads_tree,
        ).pack(side=tk.LEFT, padx=4)

        table_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "category", "size", "modified", "status")
        self.dl_tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.dl_tree.heading("name", text="File Name")
        self.dl_tree.heading("category", text="Predicted Category")
        self.dl_tree.heading("size", text="Size")
        self.dl_tree.heading("modified", text="Date Modified")
        self.dl_tree.heading("status", text="Location Status")

        self.dl_tree.column("name", width=300, anchor="w")
        self.dl_tree.column("category", width=140, anchor="w")
        self.dl_tree.column("size", width=90, anchor="e")
        self.dl_tree.column("modified", width=140, anchor="center")
        self.dl_tree.column("status", width=120, anchor="center")

        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.dl_tree.yview)
        self.dl_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.dl_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._populate_downloads_tree()

    def _populate_downloads_tree(self) -> None:
        if not hasattr(self, "dl_tree") or not self.dl_tree.winfo_exists():
            return

        for it in self.dl_tree.get_children():
            self.dl_tree.delete(it)

        folder = Path(self.config.downloads_folder)
        if not folder.exists():
            return

        try:
            for item in folder.iterdir():
                if item.is_file() and not item.name.startswith("."):
                    stat = item.stat()
                    mod_str = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    size_str = format_size(stat.st_size)

                    res = self.classifier.classify(item.name, stat.st_size, stat.st_mtime)
                    pred_cat = res.category

                    self.dl_tree.insert(
                        "",
                        tk.END,
                        values=(item.name, pred_cat, size_str, mod_str, "Unorganized (Root)"),
                    )
        except Exception as exc:
            logger.error("Error reading downloads folder: %s", exc)

    # =========================================================================
    # Page 4: Rules Page
    # =========================================================================

    def _render_rules_page(self) -> None:
        c = self.colors

        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="Organization Rules",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="Deterministic user rules with custom priority",
            font=("Segoe UI", 9),
            bg=c["bg_main"],
            fg=c["fg_muted"],
        ).pack(side=tk.LEFT, padx=12, pady=(4, 0))

        toolbar = tk.Frame(self.content_frame, bg=c["bg_main"])
        toolbar.pack(fill=tk.X, pady=(0, 10))

        tk.Button(
            toolbar,
            text="➕  Add New Rule",
            font=("Segoe UI", 9, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._show_add_rule_dialog,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            toolbar,
            text="🔄  Toggle Enable/Disable",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._toggle_rule_enabled,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            toolbar,
            text="🗑️  Delete Rule",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["danger"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._delete_selected_rule,
        ).pack(side=tk.LEFT, padx=4)

        table_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("priority", "name", "condition", "destination", "status")
        self.rules_tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.rules_tree.heading("priority", text="Priority")
        self.rules_tree.heading("name", text="Rule Name")
        self.rules_tree.heading("condition", text="Matching Condition")
        self.rules_tree.heading("destination", text="Destination Folder")
        self.rules_tree.heading("status", text="Status")

        self.rules_tree.column("priority", width=70, anchor="center")
        self.rules_tree.column("name", width=180, anchor="w")
        self.rules_tree.column("condition", width=280, anchor="w")
        self.rules_tree.column("destination", width=150, anchor="w")
        self.rules_tree.column("status", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.rules_tree.yview)
        self.rules_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.rules_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._populate_rules_tree()

    def _populate_rules_tree(self) -> None:
        if not hasattr(self, "rules_tree") or not self.rules_tree.winfo_exists():
            return

        for it in self.rules_tree.get_children():
            self.rules_tree.delete(it)

        rules = self.db.get_rules()
        for r in rules:
            cond_display = f"{r['condition_type']}: '{r['condition_value']}'"
            status_text = "Enabled" if r.get("enabled", 1) else "Disabled"
            self.rules_tree.insert(
                "",
                tk.END,
                iid=str(r["id"]),
                values=(
                    r.get("priority", 0),
                    r.get("name"),
                    cond_display,
                    r.get("destination"),
                    status_text,
                ),
            )

    def _show_add_rule_dialog(self) -> None:
        c = self.colors
        dialog = tk.Toplevel(self.root)
        dialog.title("Add New Organization Rule")
        dialog.geometry("460x380")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=c["bg_card"], padx=20, pady=16)

        tk.Label(dialog, text="Rule Name (e.g. DBMS Assignments):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        name_ent = tk.Entry(dialog, font=("Segoe UI", 9))
        name_ent.pack(fill=tk.X, pady=(2, 8))

        tk.Label(dialog, text="Condition Type:", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        cond_combo = ttk.Combobox(
            dialog,
            values=["filename_contains", "filename_starts_with", "filename_ends_with", "extension_is"],
            state="readonly",
        )
        cond_combo.set("filename_contains")
        cond_combo.pack(fill=tk.X, pady=(2, 8))

        tk.Label(dialog, text="Condition Value (e.g. dbms or .pdf):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        val_ent = tk.Entry(dialog, font=("Segoe UI", 9))
        val_ent.pack(fill=tk.X, pady=(2, 8))

        tk.Label(dialog, text="Destination Folder Name (e.g. College):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        dest_ent = tk.Entry(dialog, font=("Segoe UI", 9))
        dest_ent.pack(fill=tk.X, pady=(2, 8))

        tk.Label(dialog, text="Priority (Higher runs first, e.g. 50):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        prio_ent = tk.Entry(dialog, font=("Segoe UI", 9))
        prio_ent.insert(0, "50")
        prio_ent.pack(fill=tk.X, pady=(2, 16))

        def save():
            name = name_ent.get().strip()
            ctype = cond_combo.get().strip()
            cval = val_ent.get().strip()
            dest = dest_ent.get().strip()
            prio = int(prio_ent.get().strip() or "50")

            if not name or not cval or not dest:
                messagebox.showerror("Error", "All fields are required.")
                return

            self.db.add_rule(name=name, condition_type=ctype, condition_value=cval, destination=dest, priority=prio)
            dialog.destroy()
            self._populate_rules_tree()
            messagebox.showinfo("Rule Added", f"Rule '{name}' created successfully.")

        btn_box = tk.Frame(dialog, bg=c["bg_card"])
        btn_box.pack(fill=tk.X)
        tk.Button(btn_box, text="Save Rule", font=("Segoe UI", 9, "bold"), bg=c["accent"], fg=c["accent_fg"], relief=tk.FLAT, padx=12, pady=4, command=save).pack(side=tk.LEFT)
        tk.Button(btn_box, text="Cancel", font=("Segoe UI", 9), bg=c["bg_sidebar"], fg=c["fg_text"], relief=tk.SOLID, bd=1, padx=10, pady=4, command=dialog.destroy).pack(side=tk.LEFT, padx=6)

    def _toggle_rule_enabled(self) -> None:
        sel = self.rules_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a rule to toggle.")
            return
        rule_id = int(sel[0])
        rules = self.db.get_rules()
        r = next((x for x in rules if x["id"] == rule_id), None)
        if r:
            new_state = 0 if r.get("enabled", 1) else 1
            self.db.update_rule(
                rule_id=rule_id,
                name=r["name"],
                condition_type=r["condition_type"],
                condition_value=r["condition_value"],
                destination=r["destination"],
                enabled=bool(new_state),
                priority=r.get("priority", 0),
            )
            self._populate_rules_tree()

    def _delete_selected_rule(self) -> None:
        sel = self.rules_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a rule to delete.")
            return
        rule_id = int(sel[0])
        if messagebox.askyesno("Delete Rule", "Are you sure you want to delete this rule?"):
            self.db.delete_rule(rule_id)
            self._populate_rules_tree()

    # =========================================================================
    # Page 5: Categories Page
    # =========================================================================

    def _render_categories_page(self) -> None:
        c = self.colors

        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="Categories & Folders",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="Manage destination folders and file types",
            font=("Segoe UI", 9),
            bg=c["bg_main"],
            fg=c["fg_muted"],
        ).pack(side=tk.LEFT, padx=12, pady=(4, 0))

        toolbar = tk.Frame(self.content_frame, bg=c["bg_main"])
        toolbar.pack(fill=tk.X, pady=(0, 10))

        tk.Button(
            toolbar,
            text="➕  Add Folder / Category",
            font=("Segoe UI", 9, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._show_add_category_dialog,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            toolbar,
            text="🗑️  Delete Folder / Category",
            font=("Segoe UI", 9, "bold"),
            bg=c["bg_card"],
            fg=c["danger"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._delete_selected_category,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            toolbar,
            text="📂  Open Selected Folder",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._open_selected_category_folder,
        ).pack(side=tk.LEFT, padx=4)

        table_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("icon", "name", "folder", "extensions", "type")
        self.cat_tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.cat_tree.heading("icon", text="Icon")
        self.cat_tree.heading("name", text="Folder / Category Name")
        self.cat_tree.heading("folder", text="Subfolder Path")
        self.cat_tree.heading("extensions", text="Mapped File Extensions")
        self.cat_tree.heading("type", text="Type")

        self.cat_tree.column("icon", width=50, anchor="center")
        self.cat_tree.column("name", width=160, anchor="w")
        self.cat_tree.column("folder", width=160, anchor="w")
        self.cat_tree.column("extensions", width=360, anchor="w")
        self.cat_tree.column("type", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.cat_tree.yview)
        self.cat_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.cat_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._populate_categories_tree()

    def _populate_categories_tree(self) -> None:
        if not hasattr(self, "cat_tree") or not self.cat_tree.winfo_exists():
            return

        for it in self.cat_tree.get_children():
            self.cat_tree.delete(it)

        cats = self.db.get_categories()
        for cat in cats:
            self.cat_tree.insert(
                "",
                tk.END,
                iid=str(cat["id"]),
                values=(
                    cat.get("icon", "📁"),
                    cat.get("name"),
                    cat.get("folder"),
                    cat.get("extensions") or "(assigned via rules/others)",
                    "Default" if cat.get("is_default") else "Custom",
                ),
            )

    def _show_add_category_dialog(self) -> None:
        c = self.colors
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Folder / Category")
        dialog.geometry("450x320")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=c["bg_card"], padx=20, pady=18)

        tk.Label(dialog, text="Folder / Category Name (e.g. Photoshop or College):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        name_ent = tk.Entry(dialog, font=("Segoe UI", 10))
        name_ent.pack(fill=tk.X, pady=(2, 10))

        tk.Label(dialog, text="Subfolder Name inside Downloads (Leave blank to use Name):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        folder_ent = tk.Entry(dialog, font=("Segoe UI", 10))
        folder_ent.pack(fill=tk.X, pady=(2, 10))

        tk.Label(dialog, text="Mapped File Extensions (comma separated, e.g. .psd, .ai):", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
        exts_ent = tk.Entry(dialog, font=("Segoe UI", 10))
        exts_ent.pack(fill=tk.X, pady=(2, 16))

        def save():
            name = name_ent.get().strip()
            folder = folder_ent.get().strip() or name
            exts = exts_ent.get().strip()

            if not name:
                messagebox.showerror("Validation Error", "Folder/Category name is required.")
                return

            try:
                self.db.add_category(name=name, folder=folder, icon="📁", extensions=exts)
                target = Path(self.config.downloads_folder) / folder
                target.mkdir(parents=True, exist_ok=True)
                dialog.destroy()
                self._populate_categories_tree()
                messagebox.showinfo("Success", f"Folder '{folder}' added and mapped successfully!")
            except Exception as exc:
                messagebox.showerror("Error", f"Failed to add folder: {exc}")

        btn_frame = tk.Frame(dialog, bg=c["bg_card"])
        btn_frame.pack(fill=tk.X)
        tk.Button(btn_frame, text="Add Folder", font=("Segoe UI", 9, "bold"), bg=c["accent"], fg=c["accent_fg"], relief=tk.FLAT, padx=14, pady=5, command=save).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Cancel", font=("Segoe UI", 9), bg=c["bg_sidebar"], fg=c["fg_text"], relief=tk.SOLID, bd=1, padx=12, pady=5, command=dialog.destroy).pack(side=tk.LEFT, padx=8)

    def _delete_selected_category(self) -> None:
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a category or folder to delete.")
            return
        cat_id = int(sel[0])
        cats = self.db.get_categories()
        match = next((c for c in cats if c["id"] == cat_id), None)
        if not match:
            return

        if not messagebox.askyesno(
            "Delete Category",
            f"Are you sure you want to remove '{match['name']}' from rules?\n\nNOTE: Zero files on disk will be deleted.",
        ):
            return

        self.db.delete_category(cat_id)
        self._populate_categories_tree()
        messagebox.showinfo("Deleted", f"Category '{match['name']}' removed from rules.")

    def _open_selected_category_folder(self) -> None:
        sel = self.cat_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a category row first.")
            return
        cat_id = int(sel[0])
        cats = self.db.get_categories()
        match = next((c for c in cats if c["id"] == cat_id), None)
        if match:
            folder_name = match.get("folder") or match["name"]
            path = Path(self.config.downloads_folder) / folder_name
            self._open_specific_folder(path)

    # =========================================================================
    # Page 6: History Page
    # =========================================================================

    def _render_history_page(self) -> None:
        c = self.colors

        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="Organization History",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="Complete audit trail of all file movements",
            font=("Segoe UI", 9),
            bg=c["bg_main"],
            fg=c["fg_muted"],
        ).pack(side=tk.LEFT, padx=12, pady=(4, 0))

        toolbar = tk.Frame(self.content_frame, bg=c["bg_main"])
        toolbar.pack(fill=tk.X, pady=(0, 10))

        tk.Button(
            toolbar,
            text="↩️  Undo Selected Move",
            font=("Segoe UI", 9, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._undo_selected_history_item,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            toolbar,
            text="🔄  Refresh History",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=12,
            pady=5,
            cursor="hand2",
            command=self._populate_history_tree,
        ).pack(side=tk.LEFT, padx=4)

        table_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("time", "filename", "category", "size", "reason", "status")
        self.history_tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.history_tree.heading("time", text="Timestamp")
        self.history_tree.heading("filename", text="File Name")
        self.history_tree.heading("category", text="Category")
        self.history_tree.heading("size", text="Size")
        self.history_tree.heading("reason", text="Reason")
        self.history_tree.heading("status", text="Status")

        self.history_tree.column("time", width=130, anchor="center")
        self.history_tree.column("filename", width=220, anchor="w")
        self.history_tree.column("category", width=120, anchor="w")
        self.history_tree.column("size", width=80, anchor="e")
        self.history_tree.column("reason", width=220, anchor="w")
        self.history_tree.column("status", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._populate_history_tree()

    def _populate_history_tree(self) -> None:
        if not hasattr(self, "history_tree") or not self.history_tree.winfo_exists():
            return

        for it in self.history_tree.get_children():
            self.history_tree.delete(it)

        items = self.history.get_all_history(limit=200)
        for row in items:
            self.history_tree.insert(
                "",
                tk.END,
                iid=str(row["id"]),
                values=(
                    row.get("timestamp"),
                    row.get("filename"),
                    row.get("category"),
                    format_size(row.get("file_size", 0)),
                    row.get("reason"),
                    row.get("status"),
                ),
            )

    def _undo_selected_history_item(self) -> None:
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a history record to undo.")
            return
        hid = int(sel[0])
        self.handle_undo(hid)
        self._populate_history_tree()

    # =========================================================================
    # Page 7: Search Page
    # =========================================================================

    def _render_search_page(self) -> None:
        c = self.colors

        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="Search History",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="Instant search across SQLite database records",
            font=("Segoe UI", 9),
            bg=c["bg_main"],
            fg=c["fg_muted"],
        ).pack(side=tk.LEFT, padx=12, pady=(4, 0))

        search_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
            padx=14,
            pady=10,
        )
        search_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(search_card, text="Keyword:", font=("Segoe UI", 9, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(side=tk.LEFT, padx=(0, 6))
        self.search_ent = tk.Entry(search_card, font=("Segoe UI", 9), width=30)
        self.search_ent.pack(side=tk.LEFT, padx=(0, 12))
        self.search_ent.bind("<Return>", lambda e: self._perform_search())

        tk.Button(
            search_card,
            text="🔍  Search",
            font=("Segoe UI", 9, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            padx=12,
            pady=3,
            cursor="hand2",
            command=self._perform_search,
        ).pack(side=tk.LEFT, padx=4)

        tk.Button(
            search_card,
            text="Reset",
            font=("Segoe UI", 9),
            bg=c["bg_sidebar"],
            fg=c["fg_text"],
            relief=tk.SOLID,
            bd=1,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._reset_search,
        ).pack(side=tk.LEFT, padx=4)

        table_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("time", "filename", "category", "size", "destination", "status")
        self.search_tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.search_tree.heading("time", text="Timestamp")
        self.search_tree.heading("filename", text="File Name")
        self.search_tree.heading("category", text="Category")
        self.search_tree.heading("size", text="Size")
        self.search_tree.heading("destination", text="Destination Path")
        self.search_tree.heading("status", text="Status")

        self.search_tree.column("time", width=130, anchor="center")
        self.search_tree.column("filename", width=200, anchor="w")
        self.search_tree.column("category", width=110, anchor="w")
        self.search_tree.column("size", width=80, anchor="e")
        self.search_tree.column("destination", width=250, anchor="w")
        self.search_tree.column("status", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.search_tree.yview)
        self.search_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.search_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._perform_search()

    def _perform_search(self) -> None:
        if not hasattr(self, "search_tree") or not self.search_tree.winfo_exists():
            return
        query = self.search_ent.get().strip() if hasattr(self, "search_ent") else ""
        for it in self.search_tree.get_children():
            self.search_tree.delete(it)

        results = self.history.search(query=query, limit=100)
        for row in results:
            self.search_tree.insert(
                "",
                tk.END,
                iid=str(row["id"]),
                values=(
                    row.get("timestamp"),
                    row.get("filename"),
                    row.get("category"),
                    format_size(row.get("file_size", 0)),
                    row.get("destination_path"),
                    row.get("status"),
                ),
            )

    def _reset_search(self) -> None:
        if hasattr(self, "search_ent"):
            self.search_ent.delete(0, tk.END)
        self._perform_search()

    # =========================================================================
    # Page 8: Settings Page (with Run in Background & Exit Application)
    # =========================================================================

    def _render_settings_page(self) -> None:
        c = self.colors

        header = tk.Frame(self.content_frame, bg=c["bg_main"])
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(
            header,
            text="Settings",
            font=("Segoe UI", 18, "bold"),
            bg=c["bg_main"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        settings_card = tk.Frame(
            self.content_frame,
            bg=c["bg_card"],
            highlightbackground=c["border"],
            highlightthickness=1,
            padx=20,
            pady=16,
        )
        settings_card.pack(fill=tk.BOTH, expand=True)

        # ==========================================
        # Settings -> General
        # ==========================================
        tk.Label(
            settings_card,
            text="General",
            font=("Segoe UI", 12, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(anchor="w", pady=(0, 8))

        # 1. RUN IN BACKGROUND SETTING (Default: ON)
        self.var_run_in_background = tk.BooleanVar(value=self.config.run_in_background)
        bg_frame = tk.Frame(settings_card, bg=c["bg_card"])
        bg_frame.pack(fill=tk.X, pady=(0, 6))

        cb_bg = tk.Checkbutton(
            bg_frame,
            text="Run in Background",
            variable=self.var_run_in_background,
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_card"],
            font=("Segoe UI", 9, "bold"),
            command=self._toggle_run_in_background,
        )
        cb_bg.pack(anchor="w")

        tk.Label(
            bg_frame,
            text="   Keep Download Organizer running and organizing files when the main window is closed.",
            font=("Segoe UI", 8),
            bg=c["bg_card"],
            fg=c["fg_muted"],
        ).pack(anchor="w")

        # 2. Start with Windows Setting (Separate setting)
        self.var_start_windows = tk.BooleanVar(value=is_start_with_windows_enabled())
        win_frame = tk.Frame(settings_card, bg=c["bg_card"])
        win_frame.pack(fill=tk.X, pady=(0, 6))

        cb_win = tk.Checkbutton(
            win_frame,
            text="Start with Windows",
            variable=self.var_start_windows,
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_card"],
            font=("Segoe UI", 9),
            command=self._toggle_start_with_windows,
        )
        cb_win.pack(anchor="w")

        tk.Label(
            win_frame,
            text="   Start Download Organizer automatically when Windows boots.",
            font=("Segoe UI", 8),
            bg=c["bg_card"],
            fg=c["fg_muted"],
        ).pack(anchor="w")

        # 3. Run Minimized Setting (Separate setting)
        self.var_run_minimized = tk.BooleanVar(value=self.config.run_minimized)
        min_frame = tk.Frame(settings_card, bg=c["bg_card"])
        min_frame.pack(fill=tk.X, pady=(0, 10))

        cb_min = tk.Checkbutton(
            min_frame,
            text="Run Minimized",
            variable=self.var_run_minimized,
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_card"],
            font=("Segoe UI", 9),
            command=lambda: self.config.set("run_minimized", self.var_run_minimized.get()),
        )
        cb_min.pack(anchor="w")

        tk.Label(
            min_frame,
            text="   Start minimized to system tray on launch.",
            font=("Segoe UI", 8),
            bg=c["bg_card"],
            fg=c["fg_muted"],
        ).pack(anchor="w")

        # Divider
        tk.Frame(settings_card, bg=c["border"], height=1).pack(fill=tk.X, pady=(4, 12))

        # ==========================================
        # Folder & Organization
        # ==========================================
        tk.Label(
            settings_card,
            text="Folder & Automation",
            font=("Segoe UI", 12, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(anchor="w", pady=(0, 8))

        # Monitored Downloads Folder
        tk.Label(
            settings_card,
            text="Monitored Downloads / Target Folder",
            font=("Segoe UI", 9, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(anchor="w")

        folder_row = tk.Frame(settings_card, bg=c["bg_card"])
        folder_row.pack(fill=tk.X, pady=(4, 12))

        self.folder_var = tk.StringVar(value=self.config.downloads_folder)
        folder_ent = tk.Entry(folder_row, textvariable=self.folder_var, font=("Segoe UI", 9), state="readonly")
        folder_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        tk.Button(
            folder_row,
            text="Select Folder...",
            font=("Segoe UI", 9, "bold"),
            bg=c["accent"],
            fg=c["accent_fg"],
            relief=tk.FLAT,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._change_downloads_folder,
        ).pack(side=tk.RIGHT)

        # 4. Desktop Notifications
        self.var_notifications = tk.BooleanVar(value=self.config.notifications)
        cb_notif = tk.Checkbutton(
            settings_card,
            text="Desktop Notifications (Show Windows notification when a file is organized)",
            variable=self.var_notifications,
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_card"],
            font=("Segoe UI", 9),
            command=lambda: self.config.set("notifications", self.var_notifications.get()),
        )
        cb_notif.pack(anchor="w", pady=4)

        # 5. Automatic Organization
        self.var_auto_organize = tk.BooleanVar(value=self.config.auto_organize)
        cb_auto = tk.Checkbutton(
            settings_card,
            text="Automatic Real-Time Organization (Watch folder for new files immediately)",
            variable=self.var_auto_organize,
            bg=c["bg_card"],
            fg=c["fg_text"],
            activebackground=c["bg_card"],
            font=("Segoe UI", 9),
            command=lambda: self.config.set("auto_organize", self.var_auto_organize.get()),
        )
        cb_auto.pack(anchor="w", pady=4)

        # 6. Organization Delay
        delay_row = tk.Frame(settings_card, bg=c["bg_card"])
        delay_row.pack(fill=tk.X, pady=(10, 4))

        tk.Label(
            delay_row,
            text="Organization Delay (Stabilization wait in seconds):",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        self.var_delay = tk.IntVar(value=self.config.organization_delay)
        spin = tk.Spinbox(delay_row, from_=1, to=10, textvariable=self.var_delay, width=5, font=("Segoe UI", 9))
        spin.pack(side=tk.LEFT, padx=10)
        spin.bind("<FocusOut>", lambda e: self.config.set("organization_delay", self.var_delay.get()))

        # 7. Theme
        theme_row = tk.Frame(settings_card, bg=c["bg_card"])
        theme_row.pack(fill=tk.X, pady=4)

        tk.Label(
            theme_row,
            text="Appearance Theme:",
            font=("Segoe UI", 9),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        self.var_theme = tk.StringVar(value=self.config.theme.capitalize())
        theme_combo = ttk.Combobox(
            theme_row,
            textvariable=self.var_theme,
            values=["System", "Light", "Dark"],
            state="readonly",
            width=12,
        )
        theme_combo.pack(side=tk.LEFT, padx=10)
        theme_combo.bind("<<ComboboxSelected>>", self._on_theme_changed)

        # Divider
        tk.Frame(settings_card, bg=c["border"], height=1).pack(fill=tk.X, pady=16)

        # Diagnostic & Background Status Card (Part 14)
        diag_card = tk.Frame(settings_card, bg=c["bg_sidebar"], padx=14, pady=12, highlightbackground=c["border"], highlightthickness=1)
        diag_card.pack(fill=tk.X, pady=(0, 12))

        diag_hdr = tk.Frame(diag_card, bg=c["bg_sidebar"])
        diag_hdr.pack(fill=tk.X, pady=(0, 6))

        tk.Label(diag_hdr, text="Diagnostics & Background Status", font=("Segoe UI", 10, "bold"), bg=c["bg_sidebar"], fg=c["fg_text"]).pack(side=tk.LEFT)

        def _update_diag_labels():
            diag = self.watcher.get_diagnostics()
            lbl_diag_agent.config(text=f"Background Agent:  {diag.get('background_agent', 'UNKNOWN')}")
            lbl_diag_watcher.config(text=f"File Watcher:      {diag.get('file_watcher', 'UNKNOWN')}")
            lbl_diag_queue.config(text=f"Queue:             {diag.get('queue_size', 0)}")
            lbl_diag_event.config(text=f"Last Event:        {diag.get('last_event', 'None')}")
            lbl_diag_org.config(text=f"Last Organization: {diag.get('last_organization', 'None')}")
            lbl_diag_folder.config(text=f"Watched Folder:    {diag.get('watched_folder', '')}")

        tk.Button(diag_hdr, text="🔄 Refresh Diagnostics", font=("Segoe UI", 8), bg=c["bg_card"], fg=c["fg_text"], relief=tk.SOLID, bd=1, padx=6, pady=1, cursor="hand2", command=_update_diag_labels).pack(side=tk.RIGHT)

        diag_info = self.watcher.get_diagnostics()

        lbl_diag_agent = tk.Label(diag_card, text=f"Background Agent:  {diag_info.get('background_agent', 'UNKNOWN')}", font=("Consolas", 9), bg=c["bg_sidebar"], fg=c["fg_text"])
        lbl_diag_agent.pack(anchor="w")

        lbl_diag_watcher = tk.Label(diag_card, text=f"File Watcher:      {diag_info.get('file_watcher', 'UNKNOWN')}", font=("Consolas", 9), bg=c["bg_sidebar"], fg=c["fg_text"])
        lbl_diag_watcher.pack(anchor="w")

        lbl_diag_queue = tk.Label(diag_card, text=f"Queue:             {diag_info.get('queue_size', 0)}", font=("Consolas", 9), bg=c["bg_sidebar"], fg=c["fg_text"])
        lbl_diag_queue.pack(anchor="w")

        lbl_diag_event = tk.Label(diag_card, text=f"Last Event:        {diag_info.get('last_event', 'None')}", font=("Consolas", 9), bg=c["bg_sidebar"], fg=c["fg_text"])
        lbl_diag_event.pack(anchor="w")

        lbl_diag_org = tk.Label(diag_card, text=f"Last Organization: {diag_info.get('last_organization', 'None')}", font=("Consolas", 9), bg=c["bg_sidebar"], fg=c["fg_text"])
        lbl_diag_org.pack(anchor="w")

        lbl_diag_folder = tk.Label(diag_card, text=f"Watched Folder:    {diag_info.get('watched_folder', '')}", font=("Consolas", 9), bg=c["bg_sidebar"], fg=c["fg_text"])
        lbl_diag_folder.pack(anchor="w")

        # Advanced Test Background Monitoring (Part 15)
        test_card = tk.Frame(settings_card, bg=c["bg_card"], padx=14, pady=10, highlightbackground=c["border"], highlightthickness=1)
        test_card.pack(fill=tk.X, pady=(0, 12))

        tk.Label(test_card, text="Advanced: Test Background Monitoring", font=("Segoe UI", 10, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w", pady=(0, 4))
        tk.Label(test_card, text="Creates a safe test file (DownloadOrganizer_Test.txt) in Downloads root to verify watcher pipeline.", font=("Segoe UI", 8), bg=c["bg_card"], fg=c["fg_muted"]).pack(anchor="w", pady=(0, 6))

        lbl_test_status = tk.Label(test_card, text="", font=("Segoe UI", 8, "italic"), bg=c["bg_card"], fg=c["accent"])
        lbl_test_status.pack(anchor="w", pady=(0, 6))

        test_btn_row = tk.Frame(test_card, bg=c["bg_card"])
        test_btn_row.pack(fill=tk.X)

        def _run_test_file():
            lbl_test_status.config(text="Waiting for a test file...")
            dialog_test_path, test_name = self.watcher.create_background_test_file()
            lbl_test_status.config(text=f"Created {test_name}. Watcher event detected through normal pipeline.")
            btn_undo_test.config(state="normal")
            if self.current_page == "dashboard":
                self.refresh_dashboard()

        def _undo_test_file():
            count, msg = self.history.undo_last_batch()
            lbl_test_status.config(text=f"Test undone: {msg}")
            btn_undo_test.config(state="disabled")
            if self.current_page == "dashboard":
                self.refresh_dashboard()

        btn_run_test = tk.Button(test_btn_row, text="Test Background Monitoring", font=("Segoe UI", 8, "bold"), bg=c["accent"], fg=c["accent_fg"], relief=tk.FLAT, padx=10, pady=3, cursor="hand2", command=_run_test_file)
        btn_run_test.pack(side=tk.LEFT, padx=(0, 6))

        btn_undo_test = tk.Button(test_btn_row, text="Undo Test", font=("Segoe UI", 8), bg=c["bg_card"], fg=c["fg_text"], relief=tk.SOLID, bd=1, padx=10, pady=3, state="disabled", cursor="hand2", command=_undo_test_file)
        btn_undo_test.pack(side=tk.LEFT)

        # Divider
        tk.Frame(settings_card, bg=c["border"], height=1).pack(fill=tk.X, pady=16)

        # Explicit Exit Application Button (To completely quit when running in background)
        exit_bar = tk.Frame(settings_card, bg=c["bg_card"])
        exit_bar.pack(fill=tk.X)

        tk.Label(
            exit_bar,
            text="Completely Stop & Exit Sorty:",
            font=("Segoe UI", 9, "bold"),
            bg=c["bg_card"],
            fg=c["fg_text"],
        ).pack(side=tk.LEFT)

        tk.Button(
            exit_bar,
            text="🛑  Exit Application",
            font=("Segoe UI", 9, "bold"),
            bg=c["bg_card"],
            fg=c["danger"],
            activebackground=c["danger"],
            activeforeground="#FFFFFF",
            relief=tk.SOLID,
            bd=1,
            padx=14,
            pady=4,
            cursor="hand2",
            command=self.quit_application,
        ).pack(side=tk.RIGHT)

    def _toggle_run_in_background(self) -> None:
        val = self.var_run_in_background.get()
        self.config.set("run_in_background", val)

    def _toggle_start_with_windows(self) -> None:
        val = self.var_start_windows.get()
        success = set_start_with_windows(val)
        if success:
            self.config.set("start_with_windows", val)
        else:
            self.var_start_windows.set(not val)
            messagebox.showwarning("Notice", "Failed updating Windows startup registry.")

    def _on_theme_changed(self, event=None) -> None:
        th = self.var_theme.get().lower()
        self.config.set("theme", th)
        self._resolve_theme()
        self._setup_styles()
        self.navigate(self.current_page)

    def _change_downloads_folder(self) -> None:
        """Browse and select a new target downloads folder."""
        new_folder = filedialog.askdirectory(
            initialdir=self.config.downloads_folder,
            title="Select Folder to Organize",
            parent=self.root,
        )
        if new_folder:
            resolved = str(Path(new_folder).resolve())
            self.config.set("downloads_folder", resolved)
            self.organizer.base_downloads_folder = resolved
            self.watcher.update_watch_directory(resolved)
            if hasattr(self, "folder_var"):
                self.folder_var.set(resolved)
            self.update_status_indicator()
            if self.current_page == "dashboard":
                self.refresh_dashboard()
            messagebox.showinfo("Folder Updated", f"Sorty is now monitoring:\n{resolved}")

    # =========================================================================
    # Action Handlers: Check Downloads, 1-Click Sort, Undo, Open Folder, Close
    # =========================================================================

    def check_downloads_dialog(self) -> None:
        """
        Interactive Manual Check workflow (Part 7).
        Performs ONE explicit scan of the Downloads root, ignores category folders & temp files,
        classifies with rules, debounces with pending_files, and shows results.
        """
        c = self.colors
        dialog = tk.Toplevel(self.root)
        dialog.title("Check Downloads")
        dialog.geometry("540x440")
        dialog.minsize(460, 360)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=c["bg_main"])

        # Center dialog relative to main window
        try:
            x = self.root.winfo_x() + (self.root.winfo_width() - 540) // 2
            y = self.root.winfo_y() + (self.root.winfo_height() - 440) // 2
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

        card = tk.Frame(dialog, bg=c["bg_card"], padx=20, pady=16, highlightbackground=c["border"], highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        lbl_title = tk.Label(card, text="Checking Downloads...", font=("Segoe UI", 13, "bold"), bg=c["bg_card"], fg=c["fg_text"])
        lbl_title.pack(anchor="w", pady=(0, 10))

        content_area = tk.Frame(card, bg=c["bg_card"])
        content_area.pack(fill=tk.BOTH, expand=True)

        lbl_progress = tk.Label(content_area, text="Scanning configured Downloads root for eligible files...", font=("Segoe UI", 9), bg=c["bg_card"], fg=c["fg_muted"])
        lbl_progress.pack(anchor="w", pady=10)

        def _run_scan():
            result = self.watcher.manual_check_downloads()
            total_found = result["total_found"]
            ready_items = result["ready_to_organize"]
            already_organized = result["already_organized_count"]

            def _show_results():
                for ch in content_area.winfo_children():
                    ch.destroy()

                lbl_title.config(text="Check Complete")

                # Metrics summary (Part 7)
                summary_frame = tk.Frame(content_area, bg=c["bg_card"])
                summary_frame.pack(fill=tk.X, pady=(0, 8))

                tk.Label(summary_frame, text=f"Files found: {total_found}", font=("Segoe UI", 10), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w")
                tk.Label(summary_frame, text=f"Ready to organize: {len(ready_items)}", font=("Segoe UI", 10, "bold"), bg=c["bg_card"], fg=c["accent"]).pack(anchor="w")
                tk.Label(summary_frame, text=f"Already organized: {already_organized}", font=("Segoe UI", 10), bg=c["bg_card"], fg=c["success"]).pack(anchor="w")

                tk.Frame(content_area, bg=c["border"], height=1).pack(fill=tk.X, pady=8)

                if ready_items:
                    ready_lbl = f"{len(ready_items)} file(s) are ready to organize."
                    tk.Label(content_area, text=ready_lbl, font=("Segoe UI", 10, "bold"), bg=c["bg_card"], fg=c["fg_text"]).pack(anchor="w", pady=(0, 6))

                    # Scrollable list of ready files
                    list_box_frame = tk.Frame(content_area, bg=c["bg_sidebar"], highlightbackground=c["border"], highlightthickness=1)
                    list_box_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

                    lb_scroll = ttk.Scrollbar(list_box_frame, orient=tk.VERTICAL)
                    lb = tk.Listbox(list_box_frame, bg=c["bg_sidebar"], fg=c["fg_text"], font=("Segoe UI", 9), bd=0, highlightthickness=0, yscrollcommand=lb_scroll.set)
                    lb_scroll.config(command=lb.yview)
                    lb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
                    lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

                    for item in ready_items:
                        lb.insert(tk.END, f"  {item.filename}  →  {item.suggested_folder} ({item.reason})")

                    # Buttons: [Organize] [Cancel]
                    btn_row = tk.Frame(content_area, bg=c["bg_card"])
                    btn_row.pack(fill=tk.X)

                    def _on_organize():
                        if self.config.review_mode:
                            for it in ready_items:
                                it.state = FileState.WAITING_REVIEW
                                self.watcher.review_queue[str(it.file_path)] = it
                            dialog.destroy()
                            if self.current_page == "dashboard":
                                self.refresh_dashboard()
                            elif self.current_page == "downloads":
                                self._populate_downloads_tree()
                            messagebox.showinfo("Review Mode", f"{len(ready_items)} file(s) placed into Review Queue.")
                        else:
                            btn_org.config(state="disabled", text="Organizing...")
                            res_list = self.watcher.organize_manual_items(ready_items)
                            success_count = sum(1 for r in res_list if r.success)
                            dialog.destroy()
                            if self.current_page == "dashboard":
                                self.refresh_dashboard()
                            elif self.current_page == "recent":
                                self._render_recent_page()
                            elif self.current_page == "downloads":
                                self._populate_downloads_tree()
                            messagebox.showinfo(
                                "Check Complete",
                                f"✓ Successfully organized {success_count} file(s)!\nFiles moved to their destination folders safely.",
                            )

                    btn_org = tk.Button(
                        btn_row,
                        text="Organize",
                        font=("Segoe UI", 9, "bold"),
                        bg=c["accent"],
                        fg=c["accent_fg"],
                        relief=tk.FLAT,
                        padx=18,
                        pady=6,
                        cursor="hand2",
                        command=_on_organize,
                    )
                    btn_org.pack(side=tk.RIGHT, padx=(6, 0))

                    tk.Button(
                        btn_row,
                        text="Cancel",
                        font=("Segoe UI", 9),
                        bg=c["bg_card"],
                        fg=c["fg_text"],
                        relief=tk.SOLID,
                        bd=1,
                        padx=14,
                        pady=6,
                        cursor="hand2",
                        command=dialog.destroy,
                    ).pack(side=tk.RIGHT)

                else:
                    tk.Label(
                        content_area,
                        text="✓ All files in your Downloads root are already organized.\nNo unorganized files found.",
                        font=("Segoe UI", 9),
                        bg=c["bg_card"],
                        fg=c["success"],
                        pady=20,
                    ).pack()

                    btn_row = tk.Frame(content_area, bg=c["bg_card"])
                    btn_row.pack(fill=tk.X)
                    tk.Button(
                        btn_row,
                        text="Close",
                        font=("Segoe UI", 9),
                        bg=c["accent"],
                        fg=c["accent_fg"],
                        relief=tk.FLAT,
                        padx=16,
                        pady=6,
                        cursor="hand2",
                        command=dialog.destroy,
                    ).pack(side=tk.RIGHT)

            self.root.after(0, _show_results)

        threading.Thread(target=_run_scan, daemon=True).start()

    def manual_organize_now(self) -> None:
        """Instant 1-Click Organize all files in downloads folder."""
        folder = Path(self.config.downloads_folder)
        if not folder.exists():
            messagebox.showerror("Error", f"Folder {folder} does not exist.")
            return

        from app.watcher import TEMP_DOWNLOAD_EXTENSIONS

        files_to_sort = []
        for item in folder.iterdir():
            if item.is_file() and not item.name.startswith("."):
                if item.suffix.lower() not in TEMP_DOWNLOAD_EXTENSIONS:
                    files_to_sort.append(item)

        if not files_to_sort:
            messagebox.showinfo("Sorty", "All files in your Downloads folder are already organized! ✓")
            return

        organized = 0
        categories_used = set()
        for f in files_to_sort:
            try:
                res = self.organizer.organize_file(f)
                if res.success:
                    organized += 1
                    categories_used.add(res.category)
            except Exception as exc:
                logger.error("Failed organizing %s: %s", f.name, exc)

        if self.current_page == "dashboard":
            self.refresh_dashboard()
        elif self.current_page == "recent":
            self._render_recent_page()
        elif self.current_page == "downloads":
            self._populate_downloads_tree()

        cats_str = ", ".join(sorted(list(categories_used))[:4])
        messagebox.showinfo(
            "Sorty - Organization Complete",
            f"✓ Successfully organized {organized} file(s) into: {cats_str}\n\nAll moves are 100% reversible via Undo.",
        )

    def open_downloads_folder(self) -> None:
        """Open the active downloads directory in Windows File Explorer."""
        folder = Path(self.config.downloads_folder)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder))
        except Exception as exc:
            messagebox.showerror("Explorer Error", f"Could not open folder: {exc}")

    def _open_specific_folder(self, folder_path: Path) -> None:
        """Open specific subfolder in Windows File Explorer."""
        folder_path.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(folder_path))
        except Exception as exc:
            messagebox.showerror("Explorer Error", f"Could not open folder: {exc}")

    def handle_undo_last_batch(self) -> None:
        """1-Click Undo: Revert the last organized batch safely."""
        count, msg = self.history.undo_last_batch()
        if self.current_page == "dashboard":
            self.refresh_dashboard()
        elif self.current_page == "recent":
            self._render_recent_page()
        elif self.current_page == "history":
            self._populate_history_tree()

        if count > 0:
            messagebox.showinfo("Undo Last Sort", f"✓ {msg}")
        else:
            messagebox.showinfo("Undo Last Sort", msg)

    def handle_undo(self, history_id: int) -> None:
        """Revert a single file move safely."""
        success, msg = self.history.undo_move(history_id)
        if self.current_page == "dashboard":
            self.refresh_dashboard()
        elif self.current_page == "recent":
            self._render_recent_page()
        elif self.current_page == "history":
            self._populate_history_tree()

        if success:
            messagebox.showinfo("Undo Successful", msg)
        else:
            messagebox.showerror("Undo Failed", msg)

    def on_close_requested(self) -> None:
        """
        Handle window close event:
        If run_in_background is enabled (default True), minimize/hide to system tray.
        The watcher, organizer, and tray continue active in background.
        If run_in_background is disabled, cleanly quit the application.
        """
        if self.config.run_in_background:
            self.root.withdraw()
        else:
            self.quit_application()

    def show_window(self) -> None:
        """Thread-safe method to bring window to foreground from system tray."""
        def _do_show():
            try:
                self.root.deiconify()
                self.root.state('normal')
                self.root.lift()
                self.root.attributes('-topmost', True)
                self.root.after_idle(lambda: self.root.attributes('-topmost', False))
                self.root.focus_force()
            except Exception as exc:
                logger.debug("show_window error: %s", exc)

        self.root.after(0, _do_show)

    def set_tray_manager(self, tray_manager: Any) -> None:
        self.tray_manager = tray_manager

    def quit_application(self) -> None:
        """Thread-safe method to cleanly stop watcher, tray, and exit Sorty completely."""
        def _do_quit():
            if self.tray_manager:
                try:
                    self.tray_manager.stop()
                except Exception:
                    pass
            try:
                self.watcher.stop()
            except Exception:
                pass
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
            os._exit(0)

        if threading.current_thread() is threading.main_thread():
            _do_quit()
        else:
            try:
                self.root.after(0, _do_quit)
            except Exception:
                _do_quit()

    # =========================================================================
    # Thread-Safe Watcher Callbacks & Scheduling
    # =========================================================================

    def _on_watcher_update_threadsafe(self) -> None:
        self.root.after(0, self._refresh_ui_on_watcher_event)

    def _on_file_organized_threadsafe(self, res: OrganizerResult) -> None:
        self.root.after(0, lambda: self._handle_file_organized_ui(res))

    def _refresh_ui_on_watcher_event(self) -> None:
        if self.current_page == "dashboard":
            self._populate_recent_folders()
            self._populate_recent_activity()

    def _handle_file_organized_ui(self, res: OrganizerResult) -> None:
        if self.current_page == "dashboard":
            self.refresh_dashboard()
        elif self.current_page == "recent":
            self._render_recent_page()
        elif self.current_page == "downloads":
            self._populate_downloads_tree()
        elif self.current_page == "history":
            self._populate_history_tree()

    def _calculate_downloads_size(self) -> int:
        try:
            p = Path(self.config.downloads_folder)
            if not p.exists():
                return 0
            total = 0
            for item in p.iterdir():
                if item.is_file():
                    total += item.stat().st_size
            return total
        except Exception:
            return 0

    def refresh_dashboard(self) -> None:
        if self.current_page == "dashboard":
            self._render_dashboard()

    def _schedule_periodic_refresh(self) -> None:
        if self.current_page == "dashboard":
            self.update_status_indicator()
        self.root.after(5000, self._schedule_periodic_refresh)

    def run(self, start_minimized: bool = False) -> None:
        """Run Tkinter main event loop (watcher runs independently in background)."""
        if not self.watcher.is_running:
            self.watcher.start()
        if self.config.run_minimized or start_minimized:
            self.root.withdraw()
        self.root.mainloop()
